const { expect } = require("chai");
const { ethers } = require("hardhat");

// Role enum: None=0, Client=1, Operator=2, Admin=3, Auditor=4
const ROLE = { None: 0, Client: 1, Operator: 2, Admin: 3, Auditor: 4 };
const STATUS = { None: 0, Registered: 1, Scheduled: 2, Printing: 3, Verified: 4, Failed: 5 };

async function deploy() {
  const [admin, operator, client, other] = await ethers.getSigners();
  const acl = await (await ethers.getContractFactory("AccessControlHub")).deploy();
  await acl.waitForDeployment();
  await acl.grantRole(operator.address, ROLE.Operator);
  await acl.grantRole(client.address, ROLE.Client);
  const aclAddr = await acl.getAddress();
  const pr = await (await ethers.getContractFactory("PrinterRegistry")).deploy(aclAddr);
  await pr.waitForDeployment();
  const jr = await (await ethers.getContractFactory("JobRegistry")).deploy(aclAddr);
  await jr.waitForDeployment();
  return { acl, pr, jr, admin, operator, client, other };
}

describe("AccessControlHub", function () {
  it("sets the deployer as Admin", async function () {
    const { acl, admin } = await deploy();
    expect(await acl.has(admin.address, ROLE.Admin)).to.equal(true);
  });

  it("only Admin can grant roles", async function () {
    const { acl, client, other } = await deploy();
    await expect(acl.connect(client).grantRole(other.address, ROLE.Operator))
      .to.be.revertedWithCustomError(acl, "AccessDenied");
    await acl.grantRole(other.address, ROLE.Auditor);
    expect(await acl.has(other.address, ROLE.Auditor)).to.equal(true);
  });
});

describe("PrinterRegistry", function () {
  it("Admin adds, Operator toggles availability, Client cannot add", async function () {
    const { acl, pr, admin, operator, client } = await deploy();
    const id = ethers.encodeBytes32String("printer-01");
    await pr.connect(admin).addPrinter(id, "Prusa-MK4", "fine");
    expect(await pr.isAvailable(id)).to.equal(true);
    await pr.connect(operator).setAvailability(id, false);
    expect(await pr.isAvailable(id)).to.equal(false);
    await expect(
      pr.connect(client).addPrinter(ethers.encodeBytes32String("p2"), "X", "standard")
    ).to.be.revertedWithCustomError(acl, "AccessDenied");
  });
});

describe("JobRegistry", function () {
  it("runs the full lifecycle with role gating", async function () {
    const { jr, client, operator } = await deploy();
    const jobId = ethers.encodeBytes32String("job-1");
    const printerId = ethers.encodeBytes32String("printer-01");
    const fileHash = ethers.id("design-bytes");
    await expect(jr.connect(client).registerJob(jobId, "cid1-abc", fileHash))
      .to.emit(jr, "JobRegistered");
    expect(await jr.statusOf(jobId)).to.equal(STATUS.Registered);
    await jr.connect(operator).scheduleJob(jobId, printerId);
    expect(await jr.statusOf(jobId)).to.equal(STATUS.Scheduled);
    await jr.connect(operator).startJob(jobId);
    await jr.connect(operator).reportVerdict(jobId, true);
    expect(await jr.statusOf(jobId)).to.equal(STATUS.Verified);
  });

  it("rejects unauthorized register and illegal transitions", async function () {
    const { acl, jr, operator } = await deploy();
    const jobId = ethers.encodeBytes32String("job-2");
    await expect(jr.connect(operator).registerJob(jobId, "cid", ethers.id("x")))
      .to.be.revertedWithCustomError(acl, "AccessDenied");
    await expect(jr.connect(operator).scheduleJob(jobId, ethers.encodeBytes32String("p")))
      .to.be.revertedWithCustomError(jr, "UnknownJob");
  });
});
