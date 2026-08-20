const { expect } = require("chai");
const { ethers } = require("hardhat");

const DELAY = 3600;
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
    await expect(gov.connect(a).execute(id)).to.be.revertedWithCustomError(gov, "AlreadyFinalized");
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
    const [a] = await ethers.getSigners();
    const F = await ethers.getContractFactory("MultiSigTimelock");
    await expect(F.deploy([a.address], 2, DELAY, [])).to.be.revertedWith("bad threshold");
    await expect(F.deploy([a.address, a.address], 2, DELAY, [])).to.be.revertedWith("duplicate signer");
  });
});
