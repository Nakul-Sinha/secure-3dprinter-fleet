const { expect } = require("chai");
const { ethers } = require("hardhat");

const ROLE = { None: 0, Client: 1, Operator: 2, Admin: 3, Auditor: 4 };

async function deploy() {
  const [admin, operator, client] = await ethers.getSigners();
  const acl = await (await ethers.getContractFactory("AccessControlHub")).deploy();
  await acl.waitForDeployment();
  await acl.grantRole(operator.address, ROLE.Operator);
  await acl.grantRole(client.address, ROLE.Client);
  const reg = await (await ethers.getContractFactory("AnchorRegistry")).deploy(await acl.getAddress());
  await reg.waitForDeployment();
  return { acl, reg, admin, operator, client };
}

describe("AnchorRegistry", function () {
  it("anchors a checkpoint digest and makes it publicly verifiable", async function () {
    const { reg, operator } = await deploy();
    const digest = ethers.id("checkpoint-1");
    expect(await reg.isAnchored(digest)).to.equal(false);
    await expect(reg.connect(operator).anchor(digest)).to.emit(reg, "Anchored");
    expect(await reg.isAnchored(digest)).to.equal(true);
    expect(await reg.anchorCount()).to.equal(1);
    expect(await reg.anchoredAt(digest)).to.be.greaterThan(0);
  });

  it("rejects a non-Operator", async function () {
    const { acl, reg, client } = await deploy();
    await expect(reg.connect(client).anchor(ethers.id("x")))
      .to.be.revertedWithCustomError(acl, "AccessDenied");
  });

  it("rejects a duplicate anchor", async function () {
    const { reg, operator } = await deploy();
    const digest = ethers.id("dup");
    await reg.connect(operator).anchor(digest);
    await expect(reg.connect(operator).anchor(digest))
      .to.be.revertedWithCustomError(reg, "AlreadyAnchored");
  });

  it("returns zero time for a digest that was never anchored", async function () {
    const { reg } = await deploy();
    expect(await reg.anchoredAt(ethers.id("absent"))).to.equal(0);
  });
});
