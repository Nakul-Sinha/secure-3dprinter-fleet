const { expect } = require("chai");
const { ethers } = require("hardhat");

const V = {
  None: 0,
  VerifiedPhysical: 1,
  FailedHighConfidence: 2,
  FailedLowConfidence: 3,
  VerifiedTelemetryOnly: 4,
  Unavailable: 5,
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

const VERDICT_WINDOW = 24 * 3600;
const ARB_WINDOW = 7 * 24 * 3600;
const MIN_BOND_BPS = 2000; // bond must be at least 20 percent of payment
const AMOUNT = ethers.parseEther("1");
const BOND = ethers.parseEther("0.5");

async function deploy() {
  const [deployer, buyer, provider, verifier, arbiter, outsider] = await ethers.getSigners();
  const escrow = await (await ethers.getContractFactory("SettlementEscrow")).deploy(
    verifier.address, arbiter.address, VERDICT_WINDOW, ARB_WINDOW, MIN_BOND_BPS
  );
  await escrow.waitForDeployment();
  return { escrow, deployer, buyer, provider, verifier, arbiter, outsider };
}

async function funded(ctx, name) {
  const jobId = ethers.encodeBytes32String(name);
  const { escrow, buyer, provider } = ctx;
  const key = await escrow.dealKey(jobId, buyer.address, provider.address);
  await escrow.connect(buyer).openDeal(jobId, provider.address, BOND, { value: AMOUNT });
  await escrow.connect(provider).postBond(jobId, buyer.address, AMOUNT, { value: BOND });
  return { jobId, key };
}

async function escrowBalance(escrow) {
  return ethers.provider.getBalance(await escrow.getAddress());
}

async function drain(ctx) {
  for (const who of [ctx.buyer, ctx.provider]) {
    if ((await ctx.escrow.claimable(who.address)) > 0n) await ctx.escrow.connect(who).claim();
  }
}

describe("SettlementEscrow", function () {
  it("requires both stakes before the deal is funded", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-1");
    expect(await ctx.escrow.stateOf(key)).to.equal(S.Funded);
  });

  it("pays the provider and returns the bond on a physical verdict", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-2");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.VerifiedPhysical);
    expect(await ctx.escrow.stateOf(key)).to.equal(S.Released);
    expect(await ctx.escrow.claimable(ctx.provider.address)).to.equal(AMOUNT + BOND);
  });

  it("does not release payment on a telemetry-only verdict", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-3");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.VerifiedTelemetryOnly);
    expect(await ctx.escrow.stateOf(key)).to.equal(S.Disputed);
    expect(await ctx.escrow.claimable(ctx.provider.address)).to.equal(0n);
    expect(await ctx.escrow.claimable(ctx.buyer.address)).to.equal(0n);
  });

  it("disputes rather than slashes on a low-confidence failure", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-3b");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.FailedLowConfidence);
    expect(await ctx.escrow.stateOf(key)).to.equal(S.Disputed);
  });

  it("slashes the bond only on a high-confidence failure", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-4");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.FailedHighConfidence);
    expect(await ctx.escrow.claimable(ctx.buyer.address)).to.equal(AMOUNT + BOND);
  });

  it("holds funds when no verdict is available and never auto-refunds", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-5");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.Unavailable);
    expect(await ctx.escrow.stateOf(key)).to.equal(S.Disputed);
    expect(await ctx.escrow.claimable(ctx.buyer.address)).to.equal(0n);
    expect(await ctx.escrow.claimable(ctx.provider.address)).to.equal(0n);
  });

  it("accepts a late physical verdict while arbitration is still open", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-late");
    await ethers.provider.send("evm_increaseTime", [VERDICT_WINDOW + 1]);
    await ethers.provider.send("evm_mine", []);
    await ctx.escrow.connect(ctx.buyer).escalateStalled(key); // buyer races to dispute
    // the CT result comes back clean afterwards and must still settle
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.VerifiedPhysical);
    expect(await ctx.escrow.stateOf(key)).to.equal(S.Released);
    expect(await ctx.escrow.claimable(ctx.provider.address)).to.equal(AMOUNT + BOND);
  });

  it("refuses a verdict once arbitration has expired", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-vlate");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.Unavailable);
    await ethers.provider.send("evm_increaseTime", [ARB_WINDOW + 1]);
    await ethers.provider.send("evm_mine", []);
    await expect(ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.VerifiedPhysical))
      .to.be.revertedWithCustomError(ctx.escrow, "DeadlinePassed");
  });

  it("lets the arbiter extend arbitration so expiry means arbiter failure", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-ext");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.Unavailable);
    await ethers.provider.send("evm_increaseTime", [ARB_WINDOW - 100]);
    await ethers.provider.send("evm_mine", []);
    await ctx.escrow.connect(ctx.arbiter).extendArbitration(key);
    await ethers.provider.send("evm_increaseTime", [200]);
    await ethers.provider.send("evm_mine", []);
    await expect(ctx.escrow.unwindExpired(key))
      .to.be.revertedWithCustomError(ctx.escrow, "DeadlineNotReached");
  });

  it("unwinds neutrally if arbitration expires, so funds never stick", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-9");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.Unavailable);
    await ethers.provider.send("evm_increaseTime", [ARB_WINDOW + 1]);
    await ethers.provider.send("evm_mine", []);
    await ctx.escrow.unwindExpired(key);
    expect(await ctx.escrow.claimable(ctx.buyer.address)).to.equal(AMOUNT);
    expect(await ctx.escrow.claimable(ctx.provider.address)).to.equal(BOND);
  });

  // ---- griefing and economic attacks ----

  it("rejects a one-wei counterparty that would capture the other side's stake", async function () {
    const ctx = await deploy();
    const jobId = ethers.encodeBytes32String("grief-1");
    await ctx.escrow.connect(ctx.provider).postBond(jobId, ctx.buyer.address, AMOUNT, { value: BOND });
    // the named buyer must match the price the provider bonded against
    await expect(ctx.escrow.connect(ctx.buyer).openDeal(jobId, ctx.provider.address, BOND, { value: 1 }))
      .to.be.revertedWithCustomError(ctx.escrow, "StakeMismatch");
  });

  it("rejects a bond below the required floor", async function () {
    const ctx = await deploy();
    const jobId = ethers.encodeBytes32String("grief-2");
    // 1 wei bond against a 1 ETH job is economically meaningless
    await expect(ctx.escrow.connect(ctx.buyer).openDeal(jobId, ctx.provider.address, 1, { value: AMOUNT }))
      .to.be.revertedWithCustomError(ctx.escrow, "BondTooSmall");
  });

  it("cannot be squatted: a stranger cannot occupy a real pair's slot", async function () {
    const ctx = await deploy();
    const jobId = ethers.encodeBytes32String("grief-3");
    // outsider squats the same jobId with themselves as provider
    await ctx.escrow.connect(ctx.outsider).openDeal(jobId, ctx.provider.address, BOND, { value: AMOUNT });
    // the real buyer is unaffected, because the slot is keyed by both parties
    await ctx.escrow.connect(ctx.buyer).openDeal(jobId, ctx.provider.address, BOND, { value: AMOUNT });
    await ctx.escrow.connect(ctx.provider).postBond(jobId, ctx.buyer.address, AMOUNT, { value: BOND });
    const key = await ctx.escrow.dealKey(jobId, ctx.buyer.address, ctx.provider.address);
    expect(await ctx.escrow.stateOf(key)).to.equal(S.Funded);
  });

  it("a withdrawn slot can be reused rather than being bricked forever", async function () {
    const ctx = await deploy();
    const jobId = ethers.encodeBytes32String("grief-4");
    const key = await ctx.escrow.dealKey(jobId, ctx.buyer.address, ctx.provider.address);
    await ctx.escrow.connect(ctx.buyer).openDeal(jobId, ctx.provider.address, BOND, { value: AMOUNT });
    await ctx.escrow.connect(ctx.buyer).withdrawUnmatched(key);
    expect(await ctx.escrow.stateOf(key)).to.equal(S.None);
    // the same parties can open the job again
    await ctx.escrow.connect(ctx.buyer).openDeal(jobId, ctx.provider.address, BOND, { value: AMOUNT });
    expect(await ctx.escrow.stateOf(key)).to.equal(S.AwaitingBond);
  });

  it("rejects a zero or self counterparty", async function () {
    const ctx = await deploy();
    const jobId = ethers.encodeBytes32String("grief-5");
    await expect(ctx.escrow.connect(ctx.buyer).openDeal(jobId, ethers.ZeroAddress, BOND, { value: AMOUNT }))
      .to.be.revertedWithCustomError(ctx.escrow, "BadCounterparty");
    await expect(ctx.escrow.connect(ctx.buyer).openDeal(jobId, ctx.buyer.address, BOND, { value: AMOUNT }))
      .to.be.revertedWithCustomError(ctx.escrow, "BadCounterparty");
  });

  // ---- access control and accounting ----

  it("only the verifier may report and only the arbiter may arbitrate or extend", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-12");
    await expect(ctx.escrow.connect(ctx.provider).reportVerdict(key, V.VerifiedPhysical))
      .to.be.revertedWithCustomError(ctx.escrow, "NotAuthorized");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.Unavailable);
    await expect(ctx.escrow.connect(ctx.buyer).arbitrate(key, false, true))
      .to.be.revertedWithCustomError(ctx.escrow, "NotAuthorized");
    await expect(ctx.escrow.connect(ctx.buyer).extendArbitration(key))
      .to.be.revertedWithCustomError(ctx.escrow, "NotAuthorized");
  });

  it("pays out only through claim, and only once", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-13");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.VerifiedPhysical);
    await ctx.escrow.connect(ctx.provider).claim();
    await expect(ctx.escrow.connect(ctx.provider).claim())
      .to.be.revertedWithCustomError(ctx.escrow, "NothingToClaim");
    expect(await escrowBalance(ctx.escrow)).to.equal(0n);
  });

  it("supports claimTo so a credit can never be stranded", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-claimto");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.VerifiedPhysical);
    const before = await ethers.provider.getBalance(ctx.outsider.address);
    await ctx.escrow.connect(ctx.provider).claimTo(ctx.outsider.address);
    expect(await ethers.provider.getBalance(ctx.outsider.address)).to.equal(before + AMOUNT + BOND);
  });

  it("never lets a settled deal be settled twice", async function () {
    const ctx = await deploy();
    const { key } = await funded(ctx, "job-14");
    await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.VerifiedPhysical);
    await expect(ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.FailedHighConfidence))
      .to.be.revertedWithCustomError(ctx.escrow, "BadState");
  });

  it("conserves value EXACTLY across every terminal path", async function () {
    const paths = [
      ["verified", async (ctx, key) => ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.VerifiedPhysical)],
      ["failed", async (ctx, key) => ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.FailedHighConfidence)],
      ["arb-provider-noslash", async (ctx, key) => {
        await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.Unavailable);
        return ctx.escrow.connect(ctx.arbiter).arbitrate(key, true, false);
      }],
      ["arb-provider-slash", async (ctx, key) => {
        await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.Unavailable);
        return ctx.escrow.connect(ctx.arbiter).arbitrate(key, true, true);
      }],
      ["arb-buyer-slash", async (ctx, key) => {
        await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.Unavailable);
        return ctx.escrow.connect(ctx.arbiter).arbitrate(key, false, true);
      }],
      ["arb-buyer-noslash", async (ctx, key) => {
        await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.Unavailable);
        return ctx.escrow.connect(ctx.arbiter).arbitrate(key, false, false);
      }],
      ["unwound", async (ctx, key) => {
        await ctx.escrow.connect(ctx.verifier).reportVerdict(key, V.Unavailable);
        await ethers.provider.send("evm_increaseTime", [ARB_WINDOW + 1]);
        await ethers.provider.send("evm_mine", []);
        return ctx.escrow.unwindExpired(key);
      }],
    ];

    for (const [name, run] of paths) {
      const ctx = await deploy();
      const { key } = await funded(ctx, "conserve-" + name);
      expect(await escrowBalance(ctx.escrow)).to.equal(AMOUNT + BOND);
      await run(ctx, key);
      const credited = (await ctx.escrow.claimable(ctx.buyer.address)) +
        (await ctx.escrow.claimable(ctx.provider.address));
      // exact equality: a >= comparison cannot detect over-payment
      expect(credited, name).to.equal(AMOUNT + BOND);
      expect(await escrowBalance(ctx.escrow), name).to.equal(AMOUNT + BOND);
      await drain(ctx);
      expect(await escrowBalance(ctx.escrow), name).to.equal(0n);
    }
  });

  it("rejects an unsafe constructor configuration", async function () {
    const [, , , verifier, arbiter] = await ethers.getSigners();
    const F = await ethers.getContractFactory("SettlementEscrow");
    await expect(F.deploy(verifier.address, verifier.address, VERDICT_WINDOW, ARB_WINDOW, MIN_BOND_BPS))
      .to.be.revertedWith("verifier must not be the arbiter");
    await expect(F.deploy(verifier.address, arbiter.address, 10, ARB_WINDOW, MIN_BOND_BPS))
      .to.be.revertedWith("verdict window too short");
    await expect(F.deploy(verifier.address, arbiter.address, VERDICT_WINDOW, 10, MIN_BOND_BPS))
      .to.be.revertedWith("arbitration window too short");
  });
});
