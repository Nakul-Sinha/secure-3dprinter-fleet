const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

// Deploys the tier-A0 registries to the configured network and records their
// addresses for the backend chain adapter.
async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying with:", deployer.address);

  const acl = await (await ethers.getContractFactory("AccessControlHub")).deploy();
  await acl.waitForDeployment();
  const aclAddr = await acl.getAddress();

  const printerRegistry = await (await ethers.getContractFactory("PrinterRegistry")).deploy(aclAddr);
  await printerRegistry.waitForDeployment();

  const jobRegistry = await (await ethers.getContractFactory("JobRegistry")).deploy(aclAddr);
  await jobRegistry.waitForDeployment();

  const out = {
    network: "localhost",
    AccessControlHub: aclAddr,
    PrinterRegistry: await printerRegistry.getAddress(),
    JobRegistry: await jobRegistry.getAddress(),
    deployer: deployer.address,
  };
  const outPath = path.join(__dirname, "..", "deployments.local.json");
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
  console.log("Deployed:", out);
  console.log("Wrote", outPath);
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
