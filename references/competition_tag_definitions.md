# Competition Tag Definitions

User-provided competition reference captured on 2026-04-11.

## Tag

Main categories for classifying data based on root causes and vulnerabilities.

## DAO
- Description: Security vulnerabilities related to governance logic, permission control, voting mechanisms, member management, or cross-chain governance information verification in Decentralized Autonomous Organizations (DAOs).
- Knowledge: https://zh.wikipedia.org/zh-tw/%E5%88%86%E5%B8%83%E5%BC%8F%E8%87%AA%E6%B2%BB%E7%BB%84%E7%BB%87
- Related subtags: `State Update Inconsistency`, `Does not match with Doc`, `Bad Condition`, `Precision Loss`, `Invalid Validation`, `Centralization Risk`, `Invariant Violation`, `Implementation Error`

## DoS
- Description: When there are flaws in the logic of a contract or protocol, it can lead to certain operations such as deposits, withdrawals, transfers, proposals, liquidations, and similar actions being unable to execute successfully for an extended period or permanently. This constitutes a type of Denial of Service vulnerability. Such issues prevent the affected functionalities from being restored under unchanged contract states and hinder legitimate users from performing expected actions, often resulting in locked funds or assets, governance standoffs, or disruptions to business processes.
- Knowledge: https://blog.onesavie.com/dos-smart-contract-vulnerability-labeling-101-052d1e38a6c1
- Related subtags: `Out of Gas`, `Stale Value`, `State Update Inconsistency`, `Missing Initialization`, `Invariant Violation`, `Deprecated Library`, `Bad Condition`, `Duplicate Value`, `Front Run`, `Implementation Error`, `Invalid Validation`, `Precision Loss`, `payable / receive()`, `No Recovery Mechanism`, `Incorrect Parameter`, `Fee On Transfer Token`, `Typo`, `Missing minOut / maxAmount`, `Missing Approval`, `Execution Order Dependency`, `Missing Functionality`, `Reward Manipulation`, `Refund Failed`, `ERC777 Callback`, `Missing Upper/Lower Bound Check`, `Does not match with Doc`, `Nonce`, `1/64 Gas Rule`, `Arbitrary Add/Remove/Set/Call`, `Peg / Depeg`, `Hardcoded Parameter`, `EVM Compatibility`, `Liquidation - Dust repay / front run evade liquidation`, `Whale`, `Case Sensitive`, `Token Decimal`, `onERC721Received callback`, `Price Manipulation / Arbitrage opportunity`

## Flashloan
- Description: When a protocol relies on instantaneous states such as spot prices, real-time asset ratios, or current voting rights to calculate yields, voting rights, minting limits, and liquidity operations without implementing time-weighted mechanisms or stabilization constraints, it allows attackers to temporarily dominate the system's ratios through flash loans or large capital within a single transaction or a few blocks. This manipulation can skew calculation results, enabling them to gain undue benefits or manipulate governance outcomes before the state is restored.
- Knowledge: https://blog.onesavie.com/flashloan-attack-smart-contract-vulnerability-labeling-101-1e5a7eda30cb
- Related subtags: `Reward Manipulation`, `Whale`, `Bypass Mechanism`, `Price Manipulation / Arbitrage opportunity`, `Peg / Depeg`, `slot0`, `Incorrect Parameter`, `Bad Condition`, `State Update Inconsistency`, `Missing Time Constraint`, `Asset Theft`

## Oracle
- Description: When a protocol obtains data from on-chain or off-chain external price sources, any flaws in the selection of data sources, update frequency, verification methods, scaling conversions, or calculation methods can lead to distorted, outdated, manipulated, or unusable prices. This can affect critical functions such as trade matching, collateral liquidation, asset valuation, and minting or redeeming processes.
- Knowledge: None provided
- Related subtags: `Price Manipulation / Arbitrage opportunity`, `Incorrect Formula`, `Hardcoded Parameter`, `Token Decimal`, `Precision Loss`, `Incorrect Parameter`, `Bad Condition`, `Scaling`, `Stale Value`, `Invalid Validation`, `State Update Inconsistency`, `Duplicate Value`, `Missing Return Check`, `Misuse of Dependency`, `Unsafe Downcast`, `Does not match with Doc`, `Implementation Error`, `Bypass Mechanism`, `Rounding Error`

## Logic error
- Description: When there are logical errors in the implementation of a protocol that do not conform to the expected design or specification, such as issues with conditional statements, loop logic, index boundaries, variable update order, cross-module state synchronization, and special case handling, resulting in incorrect fund calculations, inaccurate balances or shares, incorrect states, or the inability to execute functions correctly.
- Knowledge: None provided
- Related subtags: `Bad Condition`, `Invalid Validation`, `Stale Value`, `State Update Inconsistency`, `Price Manipulation / Arbitrage opportunity`, `Incorrect Parameter`, `Does not match with Doc`, `Reward Manipulation`, `Invariant Violation`, `Bypass Mechanism`, `Missing Approval`, `Implementation Error`, `Missing Functionality`, `No Recovery Mechanism`, `Missing Upper/Lower Bound Check`, `Centralization Risk`, `Missing Return Check`, `Asset Theft`, `Out of Gas`, `Incorrect Formula`, `Unfair Liquidation`, `Cannot partial liquidations`, `Front Run`

## Reentrancy
- Description: When a contract updates critical states before implementing a locking mechanism such as `nonReentrant` or the Checks-Effects-Interactions pattern and executes external calls like `transfer`, `call`, `safeTransferFrom`, ERC777 or ERC1155 callbacks, it may allow malicious contracts or token standards with hooks to re-enter the original contract's functions or related functions during the external call. This can lead to repeated execution of business logic, circumvention of condition checks, or state alteration for the purpose of stealing assets or manipulating processes.
- Knowledge: https://blog.onesavie.com/reentrancy-smart-contract-vulnerability-labeling-101-3cb22286ed94
- Related subtags: `Violating CEI / Missing nonReentrant`, `Cross-Function Reentrancy`, `Invalid Validation`, `onERC721Received callback`, `Execution Order Dependency`, `ERC777 Callback`, `Asset Theft`, `Bypass Mechanism`

## Access Control
- Description: The lack of proper authentication, authorization checks, or controls for key functions can result in unauthorized users being able to perform operations that should only be executable by specific roles such as owner, admin, or governance. Defects in authorization revocation, role transfer, or state-checking logic can also lead to ongoing privilege leaks, which may ultimately be exploited to steal assets, compromise system configurations, or permanently lock funds.
- Knowledge: https://blog.onesavie.com/unveiling-access-control-in-ethereum-smart-contracts-common-access-control-vulnerabilities-512620e4b31b
- Related subtags: `Asset Theft`, `Arbitrary Add/Remove/Set/Call`, `Invalid Validation`, `Cannot Revoke`, `Implementation Error`, `Missing Functionality`, `Centralization Risk`, `Price Manipulation / Arbitrage opportunity`, `Role Takeover`, `Unauthorized Upgrade`, `Missing Initialization`, `State Update Inconsistency`, `Fee On Transfer Token`, `Does not match with Doc`, `Bypass Mechanism`, `Reward Manipulation`, `Bad Condition`, `Missing Upper/Lower Bound Check`, `No Recovery Mechanism`, `Incorrect Parameter`, `Front Run`, `Out of Gas`, `Duplicate Value`, `Invariant Violation`

## Liquidation
- Description: When there are design flaws in the liquidation process of lending or collateral contracts, including errors in triggering conditions, authorization checks, incentive mechanisms, calculation logic, and asset transfer steps, this can result in defaults or under-collateralized positions not being liquidated as expected, being over-liquidated, or liquidators taking advantage of logical errors to steal assets or harm the interests of other users.
- Knowledge: https://blog.onesavie.com/three-types-of-liquidation-vulnerabilities-in-defi-towards-automated-detection-using-ai-bce638142e65
- Related subtags: `Bypass Mechanism`, `Does not match with Doc`, `Invalid Validation`, `Incorrect Parameter`, `No Incentive to Liquidate`, `Bad Condition`, `Invariant Violation`, `Liquidation - Dust repay / front run evade liquidation`, `ERC777 Callback`, `Missing Functionality`, `Price Manipulation / Arbitrage opportunity`, `Unfair Liquidation`, `State Update Inconsistency`, `Cannot partial liquidations`, `Implementation Error`, `Whale`, `Out of Gas`, `Refund Failed`

## Slippage
- Description: When a contract performs operations that interact with external prices, such as executing trades, exchanging tokens, adding or removing liquidity, and minting or redeeming assets, it may lack mechanisms like minimum acceptable output (`minOut`), maximum acceptable prices, market-volatility protection, slippage protection, and deadline checks. This can cause users to suffer worse-than-expected execution and losses from price manipulation or MEV such as front-running and sandwich attacks.
- Knowledge: https://defihacklabs.substack.com/p/solidity-security-lesson-6-defi-slippage
- Related subtags: `Missing minOut / maxAmount`, `Hardcoded Parameter`, `Fee On Transfer Token`, `minOut set to 0`, `Missing deadline`, `Invalid Slippage Control / Missing slippage check`, `Incorrect Formula`

## ERC4626
- Description: When an asset pool or vault based on the ERC-4626 standard is implemented without adhering to the specification for method behavior, boundary conditions, rounding direction, or consistency between return values and state, or when its economic design permits issues such as initial deposit manipulation or share inflation attacks, the vault can become incompatible with other protocols, calculate user assets incorrectly, or suffer economic exploits.
- Knowledge: https://blog.onesavie.com/best-practices-for-implementing-an-eip-4626-compliant-vault-6b85faea9c22
- Related subtags: `Incorrect Parameter`, `Inflation Attack`, `Not EIP Compliant`, `Rounding Error`, `Price Manipulation / Arbitrage opportunity`, `Missing minOut / maxAmount`

## Input Validation
- Description: When a contract lacks proper checks on input parameters, asset or authority ownership, state validity, or invariants during critical processes such as transactions, liquidations, governance, fund transfers, or asset minting and burning, malicious or improper inputs may bypass intended restrictions. This can lead to asset theft, logical inconsistencies, irreversible system failures, or compromise of the protocol.
- Knowledge: None provided
- Related subtags: `Not EIP Compliant`, `Invalid Validation`, `Asset Theft`, `Duplicate Value`, `Precision Loss`, `Bypass Mechanism`, `Bad Condition`, `No Recovery Mechanism`, `Hardcoded Parameter`, `Does not match with Doc`, `Implementation Error`, `Incorrect Parameter`, `Reward Manipulation`, `Inflation Attack`, `Peg / Depeg`, `Price Manipulation / Arbitrage opportunity`, `Missing Time Constraint`, `Missing Upper/Lower Bound Check`, `Front Run`, `Stale Value`, `State Update Inconsistency`, `Invariant Violation`, `Nonce`

## Bad Randomness
- Description: When a contract relies on randomness to determine outcomes such as token selection, winners, validators, lottery draws, or ordering, flaws in random number generation or use can make results predictable or manipulable. Examples include using block variables, timestamps, or other miner-controllable values, letting users control the seed, missing verification of submitted results, or reusing randomness in unsafe ways.
- Knowledge: https://blog.onesavie.com/how-to-prevent-randomness-vulnerabilities-in-solidity-348f62e634cc
- Related subtags: `Bad Condition`, `Reward Manipulation`, `Front Run`

## Chainlink
- Description: When a contract relies on Chainlink oracles for prices or randomness but uses outdated APIs, omits data validity checks such as timestamp freshness, round completeness, or min and max bounds, lacks fallback mechanisms, or uses the wrong feed, it can accept stale, incorrect, or manipulable values.
- Knowledge: https://blog.onesavie.com/chainlink-smart-contract-vulnerability-labeling-101-b20674e1093d
- Related subtags: `Deprecated Library`, `Stale Value`, `Invalid Validation`, `Price Manipulation / Arbitrage opportunity`, `Missing Return Check`, `Unsafe Downcast`, `Bad Condition`, `Front Run`, `Peg / Depeg`

## Arithmetic
- Description: When there are flaws in mathematical calculation logic, including overflow, underflow, division by zero, unsafe type conversions, incorrect precision scaling, rounding direction errors, or formulas that deviate from intended design rules, the protocol can produce incorrect numerical results, asset calculations, incentives, or penalties.
- Knowledge: None provided
- Related subtags: `Unsafe Downcast`, `Token Decimal`, `Precision Loss`, `Invalid Validation`, `Scaling`, `Incorrect Formula`, `Peg / Depeg`, `Price Manipulation / Arbitrage opportunity`, `Implementation Error`, `Front Run`, `Rounding Error`, `Missing Initialization`, `Incorrect Parameter`, `Bad Condition`, `Missing Upper/Lower Bound Check`, `Stale Value`, `Bypass Mechanism`, `State Update Inconsistency`, `Block Time / Block Number`, `Hardcoded Parameter`, `Does not match with Doc`

## Re-org Attack
- Description: A vulnerability that arises when smart contract logic assumes finality or determinism in block ordering, making it exploitable via chain reorganizations that reorder or replace recent blocks.
- Knowledge: https://blog.onesavie.com/getting-to-know-reorg-attack-smart-contract-vulnerability-labeling-101-7dc7fce92630?postPublishedType=initial
- Related subtags: `State Update Inconsistency`

## Pause
- Description: When a contract provides pause mechanisms such as `Pausable`, `whenPaused`, or `whenNotPaused`, flaws in design or usage can allow disallowed operations during a paused state, omit pause checks from necessary functions, let users bypass pause restrictions, or permanently lock the system. This can result in irrecoverable state or unauthorized privileged operations.
- Knowledge: https://blog.onesavie.com/three-types-of-pause-related-vulnerabilities-smart-contract-vulnerability-labeling-101-953a44615038?postPublishedType=repub
- Related subtags: `Missing Functionality`, `Centralization Risk`, `State Update Inconsistency`, `Invalid Validation`, `1/64 Gas Rule`, `Does not match with Doc`, `Front Run`, `Invariant Violation`, `No Recovery Mechanism`

## Accounting Error
- Description: When a protocol tracks, calculates, or synchronizes assets incorrectly, discrepancies can arise between internal records and actual balances, real asset behavior may be ignored, or formulas may systematically miscompute fees, rewards, shares, or entitlements. Cross-module or cross-asset records may also update inconsistently, causing omissions or double counting.
- Knowledge: None provided
- Related subtags: `Fee On Transfer Token`, `State Update Inconsistency`, `Bad Condition`, `Incorrect Parameter`, `Peg / Depeg`, `Price Manipulation / Arbitrage opportunity`, `Reward Manipulation`, `Implementation Error`, `Incorrect Formula`, `Rebase Token`, `Asset Theft`, `Does not match with Doc`, `Invalid Validation`, `Invariant Violation`, `payable / receive()`, `Precision Loss`, `No Recovery Mechanism`, `Scaling`

## MEV
- Description: The act of maximizing extracted economic value within a blockchain system by manipulating transaction ordering, front-running transactions, or reordering transactions within a block. This usually results in losses for users or unfair resource distribution.
- Knowledge: None provided
- Related subtags: `Front Run`, `Price Manipulation / Arbitrage opportunity`, `Asset Theft`, `State Update Inconsistency`, `Reward Manipulation`, `Bad Condition`, `Execution Order Dependency`, `Bypass Mechanism`

## Upgradeable
- Description: When a contract is designed to be upgradeable through proxy patterns, module replacements, or similar mechanisms, flaws in upgrade logic, initialization, storage consistency, permission protections, or compatibility with old state can allow unauthorized upgrades, initialization oversights, or other upgrade-related vulnerabilities.
- Knowledge: https://blog.onesavie.com/4-security-pitfalls-in-upgradeable-contracts-smart-contract-vulnerability-labeling-101-495f4b316459
- Related subtags: `Centralization Risk`, `Misuse of Dependency`, `Unauthorized Upgrade`, `Storage Gap`, `Diamond`, `Missing Initialization`, `Implementation Error`, `Not EIP Compliant`, `No Recovery Mechanism`, `Invalid Validation`, `Does not match with Doc`, `Bad Condition`

## ERC20
- Description: When a contract interacts with ERC20 tokens, it may assume incorrect ERC20 behaviors, skip return-value checks, or fail to handle special token behaviors such as fee-on-transfer, rebasing, non-standard return values, and special `approve` rules. This can lead to unexpected results or vulnerabilities in contract functionality.
- Knowledge: https://blog.onesavie.com/4-erc20-risk-related-issues-every-developer-should-know-86c2359a6067
- Related subtags: `Missing Return Check`, `State Update Inconsistency`, `Not EIP Compliant`, `Fee On Transfer Token`, `No Recovery Mechanism`, `Asset Theft`, `Invalid Validation`, `Rebase Token`, `safeApprove`, `Bad Condition`, `Bypass Mechanism`, `Does not match with Doc`, `Implementation Error`, `Refund Failed`

## call / delegatecall
- Description: When a protocol uses low-level Solidity calls such as `call()`, `delegatecall()`, `staticcall()`, or inline Yul `call` instructions for transfers or cross-contract interactions and does not check whether the return value indicates success, it may update state or assume success even when the operation actually failed.
- Knowledge: None provided
- Related subtags: `Missing Return Check`

## Uniswap
- Description: When integrating with Uniswap V2, V3, or V4, implementation errors or missing safeguards in price calculation, path encoding, initialization constants, liquidity ratio calculation, and output validation can create distorted or manipulable pricing bases, corrupted path encoding, incorrect pair-location constants, bad liquidity assumptions, dust accumulation, or missing minimum-output checks.
- Knowledge: https://docs.uniswap.org/
- Related subtags: `Incorrect Formula`, `Implementation Error`, `Hardcoded Parameter`, `Inflation Attack`, `Incorrect Parameter`, `No Recovery Mechanism`, `Rounding Error`, `Price Manipulation / Arbitrage opportunity`, `slot0`, `Invalid Slippage Control / Missing slippage check`

## Cross-Chain
- Description: When a protocol implements bridges, cross-chain messaging, proposal execution, or cross-chain governance, defects in asset verification, message verification, format compatibility, state synchronization, rollback handling, permission checks, or chain ID validation can cause unsupported assets or addresses to pass through, assets to fail to return after message failure, format mismatches across chains, replay, unsynchronized state, or unauthorized cross-chain actions.
- Knowledge: None provided
- Related subtags: `Implementation Error`, `No Recovery Mechanism`, `Does not match with Doc`, `Asset Theft`, `Invalid Validation`, `Whale`, `Case Sensitive`, `Incorrect Parameter`, `Token Decimal`, `EVM Compatibility`, `State Update Inconsistency`, `Missing Initialization`, `Rebase Token`, `Bypass Mechanism`

## ERC777
- Description: When a contract performs an asset transfer that triggers an external ERC777 callback such as `tokensReceived()` or `tokensToSend()` and performs sensitive calculations or state updates before the callback occurs, it can violate Checks-Effects-Interactions and become vulnerable to reentrancy or DoS if the callback reverts.
- Knowledge: https://docs.openzeppelin.com/contracts/3.x/erc777
- Related subtags: `ERC777 Callback`, `Violating CEI / Missing nonReentrant`, `Refund Failed`, `Cross-Function Reentrancy`

## Governance
- Description: In voting power calculation, threshold checks, snapshots, proposal processes, and member management, design flaws or missing validations can let voting power be manipulated temporarily through flash loans or rapid acquisition and disposal of tokens, bypass proposal flow, cancel valid proposals, miscompute thresholds, or retain privileges after removal. Parameters or conditions may also change during voting and affect outcomes.
- Knowledge: https://blog.onesavie.com/3-interesting-takeaways-from-labeling-governance-vulnerabilities-smart-contract-vulnerability-d91354a1eab1
- Related subtags: `State Update Inconsistency`, `Invalid Validation`, `Bypass Mechanism`, `Incorrect Parameter`, `Bad Condition`, `Missing Time Constraint`, `Does not match with Doc`, `Implementation Error`, `Front Run`, `Missing Upper/Lower Bound Check`, `Invariant Violation`, `Nonce`, `Centralization Risk`, `Arbitrary Add/Remove/Set/Call`, `Missing Functionality`

## ERC1155
- Description: When a contract implements or extends the EIP-1155 multi-token standard and its business logic, flaws in standard compliance, callback handling, supply tracking, enumeration maintenance, or business validations can lead to incorrect EIP behavior, broken interoperability, inconsistent supply data, or callback-triggered reentrancy and workflow failures.
- Knowledge: https://docs.openzeppelin.com/contracts/3.x/erc1155
- Related subtags: `Not EIP Compliant`, `Reward Manipulation`, `State Update Inconsistency`, `Violating CEI / Missing nonReentrant`, `Asset Theft`, `Invalid Validation`, `Bad Condition`

## ERC721
- Description: When a contract implements or extends the EIP-721 NFT standard, flaws in standard compliance, tokenId generation and management, transfer and approval logic, callback handling, and asset protection can break interoperability, allow reentrancy or asset theft, cause tokenId duplication or ownership mismatches, or let assets be burned, hijacked, or permanently locked.
- Knowledge: https://docs.openzeppelin.com/contracts/4.x/erc721
- Related subtags: `Not EIP Compliant`, `Asset Theft`, `Invalid Validation`, `Violating CEI / Missing nonReentrant`, `onERC721Received callback`, `Duplicate Value`, `Incorrect Parameter`, `Invariant Violation`, `Missing Functionality`, `State Update Inconsistency`

## Gnosis safe
- Description: When an extension module such as a Guard, Extension, or Handler based on Gnosis Safe or other Safe-like multisig or smart-wallet systems lacks necessary authorization checks, security validation, or state management during enable, configure, disable, or parameter-validation flows.
- Knowledge: https://safe.global/
- Related subtags: `Bypass Mechanism`, `Invalid Validation`, `Invariant Violation`, `Cannot Revoke`

## Opensea
- Description: Issues related to Opensea integrations.
- Knowledge: https://blog.onesavie.com/vulnerabilities-in-opensea-seaport-integrations-smart-contract-vulnerability-labeling-101-0063f253c924
- Related subtags: `Refund Failed`, `Asset Theft`, `Invalid Validation`

## EIP712
- Description: When a contract’s signature verification or EIP-712 typed-data parsing process contains flaws such as incorrect encoding, mismatched hashing order, missing required fields, or insufficient nonce and replay protection, valid signatures may fail, invalid or replayed signatures may pass, and attackers may reuse signatures across transactions or functions.
- Knowledge: https://github.com/ethereum/EIPs/blob/master/EIPS/eip-712.md
- Related subtags: `Not EIP Compliant`, `Nonce`

## Bridge
- Description: A protocol component used for transferring assets or data between different blockchain networks such as L1, L2, or different L1 networks.
- Knowledge: None provided
- Related subtags: `Incorrect Parameter`, `Cannot Revoke`, `Invalid Validation`, `Nonce`

## Zksync
- Description: Issues related to Zksync.
- Knowledge: https://docs.zksync.io/
- Related subtags: `EVM Compatibility`, `payable / receive()`

## Replay Attack
- Description: An attacker resubmits previously executed valid messages, transactions, or data.
- Knowledge: None provided
- Related subtags: `Invalid Validation`, `Asset Theft`, `Nonce`, `State Update Inconsistency`

## Solmate
- Description: Issues related to the Solmate library.
- Knowledge: https://medium.com/onesavielab/the-most-common-risk-when-using-the-solmate-library-c3a219b6851b
- Related subtags: `Missing Return Check`

## Compound
- Description: Issues related to Compound integrations.
- Knowledge: https://docs.compound.finance/
- Related subtags: `Reward Manipulation`

## Solidity Version
- Description: Vulnerabilities caused by behaviors of specific Solidity compiler versions or optimizer errors.
- Knowledge: None provided
- Related subtags: `Misuse of Dependency`

## EIP4494
- Description: Issues related to EIP4494.
- Knowledge: https://github.com/ethereum/ercs/blob/master/ERCS/erc-4494.md
- Related subtags: `Not EIP Compliant`

## TWAP
- Description: Covers design or implementation errors related to obtaining, calculating, verifying, or using time-weighted average price data from an AMM, DEX, or oracle source. This includes incorrect TWAP formulas, failure to account for time between observations, inadequate observation windows, reliance on spot prices, mishandling of negative ticks or rounding, outdated or zero-initialized data, low-liquidity pools, missing validation of upstream oracle results, or overly strict TWAP constraints that lock assets.
- Knowledge: https://blog.onesavie.com/twap-vulnerability-smart-contract-vulnerability-labeling-101-ad75ae1623cd?postPublishedType=initial
- Related subtags: `Price Manipulation / Arbitrage opportunity`, `Implementation Error`, `Rounding Error`, `slot0`

## Subtags

Detailed classifications within each root-cause vulnerability or application-specific issue are listed above under each tag's related subtags.
