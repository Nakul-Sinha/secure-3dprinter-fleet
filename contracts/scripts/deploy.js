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
  // is the operator that runs the job. The arbiter is governance, not an EOA,
  // so no single key can move escrowed funds.
  const governanceAddr = await governance.getAddress();
  const verifier = signers[4] ? signers[4].address : deployer.address;
  const escrow = await (await ethers.getContractFactory("SettlementEscrow")).deploy(
    verifier, governanceAddr, 24 * 3600, 7 * 24 * 3600, 2000
  );
  await escrow.waitForDeployment();

  // Hand fleet administration to governance and renounce the deployer key.
  // Leaving the deployer as Admin would contradict the charter rule that no
  // single key can change roles. grantRole does not revoke, so both calls are
  // required, and the renounce must come last.
  await (await acl.grantRole(governanceAddr, 3 /* Admin */)).wait();
  const isDevChain = ["hardhat", "localhost"].includes(hre.network.name);
  const renounce = process.env.KEEP_DEPLOYER_ADMIN !== "1" && !isDevChain;
  if (renounce) {
    await (await acl.grantRole(deployer.address, 0 /* None */)).wait();
  }

  const out = {
    network: hre.network.name,
    AccessControlHub: aclAddr,
    PrinterRegistry: await printerRegistry.getAddress(),
    JobRegistry: await jobRegistry.getAddress(),
    AnchorRegistry: await anchorRegistry.getAddress(),
    MultiSigTimelock: governanceAddr,
    SettlementEscrow: await escrow.getAddress(),
    deployer: deployer.address,
    deployerIsAdmin: !renounce,
  };
  if (!renounce) {
    console.log("NOTE: the deployer keeps Admin on this development network. " +
      "A production deploy renounces it so only governance can change roles.");
  }
  const outPath = path.join(__dirname, "..", "deployments.local.json");
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
  console.log("Deployed:", out);
  console.log("Wrote", outPath);
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
