const { expect } = require("chai");
const { ethers } = require("hardhat");

const V = {
  None: 0,
  VerifiedPhysical: 1,
  FailedHighConfidence: 2,
  FailedLowConfidence: 3,
  Unavailable: 4,
};
const S = {
  None: 0,
  AwaitingBond: 1,
  AwaitingPayment: 2,
  Funded: 3,
  Released: 4,
  Refunded: 5,
  Disputed: 6,
  Unwound: 7,
};

const VERDICT_WINDOW = 3600;
const ARB_WINDOW = 7200;
const AMOUNT = ethers.parseEther("1");
const BOND = ethers.parseEther("0.5");

async function deploy() {
  const [deployer, buyer, provider, verifier, arbiter] = await ethers.getSigners();
  const escrow = await (await ethers.getContractFactory("SettlementEscrow")).deploy(
    verifier.address, arbiter.address, VERDICT_WINDOW, ARB_WINDOW
  );
  await escrow.waitForDeployment();
  return { escrow, deployer, buyer, provider, verifier, arbiter };
}

async function funded(ctx, jobId) {
  const { escrow, buyer, provider } = ctx;
  await escrow.connect(buyer).openDeal(jobId, provider.address, { value: AMOUNT });
  await escrow.connect(provider).postBond(jobId, { value: BOND });
  return jobId;
}

describe("SettlementEscrow", function () {
  it("requires both payment and bond before work is considered funded", async function () {
    const ctx = await deploy();
    const id = ethers.encodeBytes32String("job-1");
    await ctx.escrow.connect(ctx.buyer).openDeal(id, ctx.provider.address, { value: AMOUNT });
    expect(await ctx.escrow.stateOf(id)).to.equal(S.AwaitingBond);
    await ctx.escrow.connect(ctx.provider).postBond(id, { value: BOND });
    expect(await ctx.escrow.stateOf(id)).to.equal(S.Funded);
  });

  it("pays the provider and returns the bond on a physical verdict", async function () {
    const ctx = await deploy();
    const id = await funded(ctx, ethers.encodeBytes32String("job-2"));
    await ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.VerifiedPhysical);
    expect(await ctx.escrow.stateOf(id)).to.equal(S.Released);
    expect(await ctx.escrow.claimable(ctx.provider.address)).to.equal(AMOUNT + BOND);
    expect(await ctx.escrow.claimable(ctx.buyer.address)).to.equal(0n);
  });

  it("does NOT release payment on a telemetry-only verdict", async function () {
    const ctx = await deploy();
    const id = await funded(ctx, ethers.encodeBytes32String("job-3"));
    // low confidence must never pay out; it goes to dispute instead
    await ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.FailedLowConfidence);
    expect(await ctx.escrow.stateOf(id)).to.equal(S.Disputed);
    expect(await ctx.escrow.claimable(ctx.provider.address)).to.equal(0n);
    expect(await ctx.escrow.claimable(ctx.buyer.address)).to.equal(0n);
  });

  it("slashes the bond only on a high-confidence failure", async function () {
    const ctx = await deploy();
    const id = await funded(ctx, ethers.encodeBytes32String("job-4"));
    await ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.FailedHighConfidence);
    expect(await ctx.escrow.stateOf(id)).to.equal(S.Refunded);
    expect(await ctx.escrow.claimable(ctx.buyer.address)).to.equal(AMOUNT + BOND);
  });

  it("holds funds when no verdict is available, never auto-refunds", async function () {
    const ctx = await deploy();
    const id = await funded(ctx, ethers.encodeBytes32String("job-5"));
    await ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.Unavailable);
    expect(await ctx.escrow.stateOf(id)).to.equal(S.Disputed);
    // a buyer who stalls the verifier gains nothing
    expect(await ctx.escrow.claimable(ctx.buyer.address)).to.equal(0n);
    expect(await ctx.escrow.claimable(ctx.provider.address)).to.equal(0n);
  });

  it("lets anyone escalate a stalled deal after the verdict window", async function () {
    const ctx = await deploy();
    const id = await funded(ctx, ethers.encodeBytes32String("job-6"));
    await expect(ctx.escrow.connect(ctx.buyer).escalateStalled(id))
      .to.be.revertedWithCustomError(ctx.escrow, "DeadlineNotReached");
    await ethers.provider.send("evm_increaseTime", [VERDICT_WINDOW + 1]);
    await ethers.provider.send("evm_mine", []);
    await ctx.escrow.connect(ctx.buyer).escalateStalled(id);
    expect(await ctx.escrow.stateOf(id)).to.equal(S.Disputed);
  });

  it("resolves a dispute for the provider without slashing", async function () {
    const ctx = await deploy();
    const id = await funded(ctx, ethers.encodeBytes32String("job-7"));
    await ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.FailedLowConfidence);
    await ctx.escrow.connect(ctx.arbiter).arbitrate(id, true, false);
    expect(await ctx.escrow.stateOf(id)).to.equal(S.Released);
    expect(await ctx.escrow.claimable(ctx.provider.address)).to.equal(AMOUNT + BOND);
  });

  it("resolves a dispute for the buyer with slashing", async function () {
    const ctx = await deploy();
    const id = await funded(ctx, ethers.encodeBytes32String("job-8"));
    await ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.Unavailable);
    await ctx.escrow.connect(ctx.arbiter).arbitrate(id, false, true);
    expect(await ctx.escrow.claimable(ctx.buyer.address)).to.equal(AMOUNT + BOND);
    expect(await ctx.escrow.claimable(ctx.provider.address)).to.equal(0n);
  });

  it("unwinds neutrally if arbitration itself expires, so funds never stick", async function () {
    const ctx = await deploy();
    const id = await funded(ctx, ethers.encodeBytes32String("job-9"));
    await ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.Unavailable);
    await expect(ctx.escrow.unwindExpired(id))
      .to.be.revertedWithCustomError(ctx.escrow, "DeadlineNotReached");
    await ethers.provider.send("evm_increaseTime", [ARB_WINDOW + 1]);
    await ethers.provider.send("evm_mine", []);
    await ctx.escrow.unwindExpired(id);
    expect(await ctx.escrow.stateOf(id)).to.equal(S.Unwound);
    // each side gets its own money back: nobody profits from stalling
    expect(await ctx.escrow.claimable(ctx.buyer.address)).to.equal(AMOUNT);
    expect(await ctx.escrow.claimable(ctx.provider.address)).to.equal(BOND);
  });

  it("lets a provider reclaim a bond if the buyer never funds", async function () {
    const ctx = await deploy();
    const id = ethers.encodeBytes32String("job-10");
    await ctx.escrow.connect(ctx.provider).postBond(id, { value: BOND });
    expect(await ctx.escrow.stateOf(id)).to.equal(S.AwaitingPayment);
    await ctx.escrow.connect(ctx.provider).withdrawUnmatched(id);
    expect(await ctx.escrow.claimable(ctx.provider.address)).to.equal(BOND);
  });

  it("lets a buyer withdraw if the provider never bonds", async function () {
    const ctx = await deploy();
    const id = ethers.encodeBytes32String("job-11");
    await ctx.escrow.connect(ctx.buyer).openDeal(id, ctx.provider.address, { value: AMOUNT });
    await ctx.escrow.connect(ctx.buyer).withdrawUnmatched(id);
    expect(await ctx.escrow.claimable(ctx.buyer.address)).to.equal(AMOUNT);
  });

  it("only the verifier may report and only the arbiter may arbitrate", async function () {
    const ctx = await deploy();
    const id = await funded(ctx, ethers.encodeBytes32String("job-12"));
    await expect(ctx.escrow.connect(ctx.provider).reportVerdict(id, V.VerifiedPhysical))
      .to.be.revertedWithCustomError(ctx.escrow, "NotAuthorized");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.Unavailable);
    await expect(ctx.escrow.connect(ctx.buyer).arbitrate(id, false, true))
      .to.be.revertedWithCustomError(ctx.escrow, "NotAuthorized");
  });

  it("pays out only through claim, and only once", async function () {
    const ctx = await deploy();
    const id = await funded(ctx, ethers.encodeBytes32String("job-13"));
    await ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.VerifiedPhysical);
    const before = await ethers.provider.getBalance(ctx.provider.address);
    await ctx.escrow.connect(ctx.provider).claim();
    const after = await ethers.provider.getBalance(ctx.provider.address);
    expect(after).to.be.greaterThan(before);
    await expect(ctx.escrow.connect(ctx.provider).claim())
      .to.be.revertedWithCustomError(ctx.escrow, "NothingToClaim");
  });

  it("never lets a settled deal be settled twice", async function () {
    const ctx = await deploy();
    const id = await funded(ctx, ethers.encodeBytes32String("job-14"));
    await ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.VerifiedPhysical);
    await expect(ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.FailedHighConfidence))
      .to.be.revertedWithCustomError(ctx.escrow, "BadState");
  });

  it("conserves value across every terminal state", async function () {
    const ctx = await deploy();
    for (const [name, fn] of [
      ["verified", async (id) => ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.VerifiedPhysical)],
      ["failed", async (id) => ctx.escrow.connect(ctx.verifier).reportVerdict(id, V.FailedHighConfidence)],
    ]) {
      const id = await funded(ctx, ethers.encodeBytes32String("conserve-" + name));
      await fn(id);
      const total = (await ctx.escrow.claimable(ctx.buyer.address)) +
        (await ctx.escrow.claimable(ctx.provider.address));
      expect(total).to.be.greaterThanOrEqual(AMOUNT + BOND);
      // drain for the next iteration
      if ((await ctx.escrow.claimable(ctx.buyer.address)) > 0n) await ctx.escrow.connect(ctx.buyer).claim();
      if ((await ctx.escrow.claimable(ctx.provider.address)) > 0n) await ctx.escrow.connect(ctx.provider).claim();
    }
  });

  it("refuses a verifier that is also the arbiter", async function () {
    const [, , , verifier] = await ethers.getSigners();
    const F = await ethers.getContractFactory("SettlementEscrow");
    await expect(F.deploy(verifier.address, verifier.address, 10, 10))
      .to.be.revertedWith("verifier must not be the arbiter");
  });
});
