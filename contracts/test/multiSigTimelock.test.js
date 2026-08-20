const { expect } = require("chai");
const { ethers } = require("hardhat");

const DELAY = 24 * 3600; // the contract enforces a 24h floor
const ROLE = { None: 0, Client: 1, Operator: 2, Admin: 3, Auditor: 4 };

async function deploy() {
  const [a, b, c, guardian, outsider, target] = await ethers.getSigners();
  const gov = await (await ethers.getContractFactory("MultiSigTimelock")).deploy(
    [a.address, b.address, c.address], 2, DELAY, [guardian.address]
  );
  await gov.waitForDeployment();
  return { gov, a, b, c, guardian, outsider, target };
}

// A queued call that grants a role on AccessControlHub, so the test exercises
// governance driving a real fleet action rather than a toy target.
async function withAcl(gov) {
  const acl = await (await ethers.getContractFactory("AccessControlHub")).deploy();
  await acl.waitForDeployment();
  // hand admin rights to governance
  await acl.grantRole(await gov.getAddress(), ROLE.Admin);
  return acl;
}

describe("MultiSigTimelock", function () {
  it("requires the threshold of approvals before execution", async function () {
    const { gov, a, b } = await deploy();
    const acl = await withAcl(gov);
    const data = acl.interface.encodeFunctionData("grantRole", [b.address, ROLE.Operator]);
    const salt = ethers.id("op-1");
    const id = await gov.operationId(await acl.getAddress(), 0, data, salt);
    await gov.connect(a).queue(await acl.getAddress(), 0, data, salt);

    await ethers.provider.send("evm_increaseTime", [DELAY + 1]);
    await ethers.provider.send("evm_mine", []);
    // one approval is not enough
    await expect(gov.connect(a).execute(id))
      .to.be.revertedWithCustomError(gov, "NotEnoughApprovals");

    await gov.connect(b).approve(id);
    await gov.connect(a).execute(id);
    expect(await acl.has(b.address, ROLE.Operator)).to.equal(true);
  });

  it("enforces the delay even with enough approvals", async function () {
    const { gov, a, b, target } = await deploy();
    const salt = ethers.id("op-2");
    const id = await gov.operationId(target.address, 0, "0x", salt);
    await gov.connect(a).queue(target.address, 0, "0x", salt);
    await gov.connect(b).approve(id);
    await expect(gov.connect(a).execute(id)).to.be.revertedWithCustomError(gov, "NotReady");
  });

  it("lets a guardian cancel but never execute", async function () {
    const { gov, a, b, guardian, target } = await deploy();
    const salt = ethers.id("op-3");
    const id = await gov.operationId(target.address, 0, "0x", salt);
    await gov.connect(a).queue(target.address, 0, "0x", salt);
    await gov.connect(b).approve(id);
    await expect(gov.connect(guardian).execute(id)).to.be.revertedWithCustomError(gov, "NotSigner");
    await gov.connect(guardian).cancel(id);
    await ethers.provider.send("evm_increaseTime", [DELAY + 1]);
    await ethers.provider.send("evm_mine", []);
    await expect(gov.connect(a).execute(id)).to.be.revertedWithCustomError(gov, "UnknownOperation");
  });

  it("does not let one signer veto the majority", async function () {
    const { gov, a, b, c, target } = await deploy();
    const salt = ethers.id("op-veto");
    const id = await gov.operationId(target.address, 0, "0x", salt);
    await gov.connect(a).queue(target.address, 0, "0x", salt);
    await gov.connect(b).approve(id);
    // a lone dissenting signer must not be able to kill the action
    await expect(gov.connect(c).cancel(id)).to.be.revertedWithCustomError(gov, "NotGuardian");
    await ethers.provider.send("evm_increaseTime", [DELAY + 1]);
    await ethers.provider.send("evm_mine", []);
    await gov.connect(a).execute(id);
  });

  it("allows a cancelled action to be proposed again from a clean slate", async function () {
    const { gov, a, b, guardian, target } = await deploy();
    const salt = ethers.id("op-requeue");
    const id = await gov.operationId(target.address, 0, "0x", salt);
    await gov.connect(a).queue(target.address, 0, "0x", salt);
    await gov.connect(guardian).cancel(id);
    // same action, proposed again: approvals start fresh
    await gov.connect(a).queue(target.address, 0, "0x", salt);
    expect(await gov.approved(id, a.address)).to.equal(true);
    expect(await gov.approved(id, b.address)).to.equal(false);
    await gov.connect(b).approve(id);
    await ethers.provider.send("evm_increaseTime", [DELAY + 1]);
    await ethers.provider.send("evm_mine", []);
    await gov.connect(a).execute(id);
  });

  it("rotates signers only through its own timelock", async function () {
    const { gov, a, b, outsider } = await deploy();
    // a direct call must fail: rotation needs M-of-N plus the delay
    await expect(gov.connect(a).addSigner(outsider.address)).to.be.revertedWithCustomError(gov, "NotSigner");

    const data = gov.interface.encodeFunctionData("addSigner", [outsider.address]);
    const salt = ethers.id("op-rotate");
    const id = await gov.operationId(await gov.getAddress(), 0, data, salt);
    await gov.connect(a).queue(await gov.getAddress(), 0, data, salt);
    await gov.connect(b).approve(id);
    await ethers.provider.send("evm_increaseTime", [DELAY + 1]);
    await ethers.provider.send("evm_mine", []);
    await gov.connect(a).execute(id);
    expect(await gov.isSigner(outsider.address)).to.equal(true);
    expect(await gov.signerCount()).to.equal(4n);
  });

  it("refuses to remove a signer below the threshold", async function () {
    const { gov, a, b, c } = await deploy();
    const data = gov.interface.encodeFunctionData("removeSigner", [c.address]);
    const salt = ethers.id("op-remove");
    const id = await gov.operationId(await gov.getAddress(), 0, data, salt);
    await gov.connect(a).queue(await gov.getAddress(), 0, data, salt);
    await gov.connect(b).approve(id);
    await ethers.provider.send("evm_increaseTime", [DELAY + 1]);
    await ethers.provider.send("evm_mine", []);
    // 3 signers, threshold 2: removing one is allowed
    await gov.connect(a).execute(id);
    expect(await gov.signerCount()).to.equal(2n);

    // removing another would drop below the threshold
    const data2 = gov.interface.encodeFunctionData("removeSigner", [b.address]);
    const salt2 = ethers.id("op-remove-2");
    const id2 = await gov.operationId(await gov.getAddress(), 0, data2, salt2);
    await gov.connect(a).queue(await gov.getAddress(), 0, data2, salt2);
    await gov.connect(b).approve(id2);
    await ethers.provider.send("evm_increaseTime", [DELAY + 1]);
    await ethers.provider.send("evm_mine", []);
    await expect(gov.connect(a).execute(id2)).to.be.revertedWithCustomError(gov, "CallFailed");
  });

  it("rejects non-signers and double approval", async function () {
    const { gov, a, outsider, target } = await deploy();
    const salt = ethers.id("op-4");
    const id = await gov.operationId(target.address, 0, "0x", salt);
    await gov.connect(a).queue(target.address, 0, "0x", salt);
    await expect(gov.connect(outsider).approve(id)).to.be.revertedWithCustomError(gov, "NotSigner");
    await expect(gov.connect(a).approve(id)).to.be.revertedWithCustomError(gov, "AlreadyApproved");
  });

  it("cannot execute the same operation twice", async function () {
    const { gov, a, b, target } = await deploy();
    const salt = ethers.id("op-5");
    const id = await gov.operationId(target.address, 0, "0x", salt);
    await gov.connect(a).queue(target.address, 0, "0x", salt);
    await gov.connect(b).approve(id);
    await ethers.provider.send("evm_increaseTime", [DELAY + 1]);
    await ethers.provider.send("evm_mine", []);
    await gov.connect(a).execute(id);
    await expect(gov.connect(a).execute(id)).to.be.revertedWithCustomError(gov, "AlreadyFinalized");
  });

  it("rejects a bad constructor configuration", async function () {
    const [a, b] = await ethers.getSigners();
    const F = await ethers.getContractFactory("MultiSigTimelock");
    await expect(F.deploy([a.address], 2, DELAY, [])).to.be.revertedWith("bad threshold");
    await expect(F.deploy([a.address, a.address], 2, DELAY, [])).to.be.revertedWith("duplicate signer");
    await expect(F.deploy([a.address, b.address], 2, 60, [])).to.be.revertedWith("delay too short");
  });
});
