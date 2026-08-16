const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("PlatformInfo", function () {
  it("deploys and reports platform, version, and ping", async function () {
    const Factory = await ethers.getContractFactory("PlatformInfo");
    const info = await Factory.deploy("0.1.0");
    await info.waitForDeployment();

    expect(await info.platform()).to.equal("Secure 3D-Printer Fleet");
    expect(await info.version()).to.equal("0.1.0");
    expect(await info.ping()).to.equal("ok");

    const [signer] = await ethers.getSigners();
    expect(await info.deployer()).to.equal(signer.address);
  });

  it("emits Deployed on construction", async function () {
    const Factory = await ethers.getContractFactory("PlatformInfo");
    const info = await Factory.deploy("9.9.9");
    await expect(info.deploymentTransaction())
      .to.emit(info, "Deployed");
    expect(await info.version()).to.equal("9.9.9");
  });
});
