const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

// Phase 0 deploy probe. Phase A extends this to deploy the registries and
// write their addresses to a file the backend reads.
async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying with:", deployer.address);

  const Factory = await ethers.getContractFactory("PlatformInfo");
  const info = await Factory.deploy("0.1.0");
  await info.waitForDeployment();
  const address = await info.getAddress();
  console.log("PlatformInfo deployed at:", address);

  const out = { PlatformInfo: address, network: "localhost" };
  const outPath = path.join(__dirname, "..", "deployments.local.json");
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
  console.log("Wrote", outPath);
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
