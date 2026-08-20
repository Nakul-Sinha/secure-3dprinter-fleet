const hre = require("hardhat");
const { ethers } = hre;
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

  const anchorRegistry = await (await ethers.getContractFactory("AnchorRegistry")).deploy(aclAddr);
  await anchorRegistry.waitForDeployment();

  // Governance: signers and guardian are distinct accounts, and the delay gives
  // time to notice and cancel a hostile action before it executes.
  const signers = await ethers.getSigners();
  const govSigners = signers.slice(0, 3).map((s) => s.address);
  const guardian = signers[3] ? [signers[3].address] : [];
  const governance = await (await ethers.getContractFactory("MultiSigTimelock")).deploy(
    govSigners, 2, 48 * 3600, guardian
  );
  await governance.waitForDeployment();

  // Escrow: the verifier and the arbiter must be different parties, and neither
  // is the operator that runs the job.
  const verifier = signers[4] ? signers[4].address : deployer.address;
  const arbiter = signers[5] ? signers[5].address : await governance.getAddress();
  const escrow = await (await ethers.getContractFactory("SettlementEscrow")).deploy(
    verifier, arbiter, 24 * 3600, 7 * 24 * 3600
  );
  await escrow.waitForDeployment();

  const out = {
    network: hre.network.name,
    AccessControlHub: aclAddr,
    PrinterRegistry: await printerRegistry.getAddress(),
    JobRegistry: await jobRegistry.getAddress(),
    AnchorRegistry: await anchorRegistry.getAddress(),
    MultiSigTimelock: await governance.getAddress(),
    SettlementEscrow: await escrow.getAddress(),
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
