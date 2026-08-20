require("@nomicfoundation/hardhat-toolbox");

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
    },
  },
  networks: {
    hardhat: {},
    localhost: {
      url: "http://127.0.0.1:8545",
    },
    // Permissioned consortium (tier A1). See infra/besu.
    besu: {
      url: process.env.BESU_RPC || "http://127.0.0.1:8545",
      gasPrice: 0,
    },
  },
  mocha: {
    timeout: 120000,
  },
};
