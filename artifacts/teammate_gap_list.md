# Teammate labeling worklist — Bastet under-covered test repos

**Goal:** v11 covers 400/400 rows but UNDER-covers these repos vs the canonical audit report.
Because the submission is a hard 400-row cap, the value is twofold:
1. **Fill TRUTH (severity/tag/subtag/description) in dataset_0831 for the listed findings** so we can upgrade v11's existing (sometimes guessed) rows to match truth exactly — pure upside, no row swap.
2. Where a missing finding is clearly higher-value than a current weak row, we can do a targeted swap.

**Total canonical findings missing across 18 repos: 98.** Prioritized by gap size.

## 2023-01-popcorn  (`e0d2d83ea351`) — have 14 / canonical 47  → **+33 missing**
   1. [H] Any user can drain the entire reward fund in MultiRewardStaking due to incorrect calculation of `supplierDelta
   2. [H] `BeefyAdapter()` malicious vault owner can use malicious `\_beefyBooster` to steal the adapter's token
   3. [H] Incorrect Reward Duration After Change in Reward Speed in MultiRewardStaking
   4. [H] Staking rewards can be drained
   5. [H] Malicious strategy can lead to loss of funds
   6. [H] Lost Rewards in MultiRewardStaking Upon Third-Party Withdraw
   7. [H] Anyone who uses same adapter has the ability to pause it
   8. [H] Attacker can deploy vaults with a malicious Staking contract
   9. [H] Attacker can steal 99% of total balance from any reward token in any Staking contract
  10. [H] First vault depositor can steal other's assets
  11. [H] Protocol loses fees because highWaterMark is updated every time someone deposit, withdraw, mint
  12. [H] Modifier VaultController._verifyCreatorOrOwner does not work as intented
  13. [M] Vault creator can prevent users from claiming staking rewards
  14. [M] `quitPeriod` is effectively always just `1 day`
  15. [M] `Vault::takeFees` can be front run to minimize `accruedPerformanceFee`
  16. [M] Total assets of yearn vault are not correct
  17. [M] Adapters logic contracts can be destroyed
  18. [M] In `MultiRewardStaking.addRewardToken()`, `rewardsPerSecond` is not accurate enough to handle all type of rewa
  19. [M] Users can fail to withdraw deposited assets from a vault that uses `YearnAdapter` contract as its adapter beca
  20. [M] `VaultController()` Missing call `DeploymentController.nominateNewDependencyOwner()`
  21. [M] cool down time period is not properly respected for the `harvest` method
  22. [M] `Vault.redeem` function does not use `syncFeeCheckpoint` modifier
  23. [M] Unchecked return of `execute()`
  24. [M] Vault Fees Can Total To More Than `1e18`
  25. [M] vault.changeAdapter can be misused to drain fees
  26. [M] Fee on transfer token not supported
  27. [M] Management Fee for a vault is charged even when there is no assets under management and subject to manipulatio
  28. [M] The calculation of ````takeFees```` in ````Vault```` contract is incorrect
  29. [M] Malicious Users Can Drain The Assets Of Vault. (Due to not being ERC4626 Complaint)
  30. [M] Strategy can't earn yields for user as underlyingBalance is not updated when strategy deposits
  31. [M] Owner can collect management fees with a new increased fee for previous time period.
  32. [M] erc777 cross function re-entrancy
  33. [M] AdapterBase should always use delegatecall to call the functions in the strategy
  34. [M] Vault fees can be set to anything when initializing
  35. [M] `syncFeeCheckpoint()` does not modify the highWaterMark correctly, sometimes it might even decrease its value,
  36. [M] Accrued perfomance fee calculation takes wrong assumptions for share decimals, leading to loss of shares or hy
  37. [M] AdpaterBase.harvest should be called before deposit and withdraw
  38. [M] `**Harvest()**` may not be executed when changing a **Vault** adapter
  39. [M] Faulty Escrow config will lock up reward tokens in Staking contract
  40. [M] Reentrancy abuse to reduce the minted management fees when changing an adapter
  41. [M] `MultiRewardStaking.changeRewardSpeed()` breaks the distribution
  42. [M] Vault creator can't change quitPeriod
  43. [M] Vault creator can't change feeRecipient after deployment
  44. [M] DOS any Staking contract with Arithmetic Overflow
  45. [M] Users lose their entire investment when making a deposit and resulting shares are zero
  46. [M] Anyone can reset fees to 0 value when Vault is deployed
  47. [M] Vault.maxWithdraw returns asset amount that is too big for Vault.withdraw

## 2022-08-frax  (`54405135ebf3`) — have 3 / canonical 15  → **+12 missing**
   1. [H] Any borrower with bad debt can be liquidated multiple times to lock funds in the lending pair
   2. [H] `liquidate()` doesn't mark off bad debt, leading to a 'last lender to withdraw loses' scenario
   3. [M] Penalty rate is used for pre-maturity date as well
   4. [M] Interest can be significantly lower if `addInterest` isn't called frequently enough
   5. [M] Impossible to `setCreationCode()` with code size less than 13K
   6. [M] Wrong percent for `FraxlendPairCore.dirtyLiquidationFee`.
   7. [M] Liquidator might end up paying much more asset than collateral received
   8. [M] FraxlendPair#setTimeLock: Allows the owner to reset TIME_LOCK_ADDRESS
   9. [M] FraxlendPair.changeFee() doesn't update interest before changing fee.
  10. [M] Owner of `FraxlendPair` can set arbitrary time lock contract address to circumvent time lock
  11. [M] FraxlendPair.sol is not fully EIP-4626 compliant
  12. [M] Decimals limitation limits the tokens that can be used
  13. [M] Fraxlend pair deployment can be front-run by a custom pair deployment
  14. [M] Denial of service in globalPause by wrong logic
  15. [M] No incentives to write off bad debt when remaining collateral is very small

## 2022-06-nibbl  (`198fa93fabdd`) — have 2 / canonical 12  → **+10 missing**
   1. [M] Buyout cannot be rejected when paused
   2. [M] `Twav.sol#_getTwav()` will revert when timestamp > 4294967296
   3. [M] User Could Change The State Of The System While In `Pause` Mode
   4. [M] Ineffective TWAV Implementation
   5. [M] Lack of sanity check on _initialTokenSupply and _initialTokenPrice can lead to a seller losing his NFT
   6. [M] NibblVault: In the buy function, users can avoid paying fees
   7. [M] `_updateTwav()` and `_getTwav()` will revert when cumulativePrice overflows
   8. [M] PNM-004 Calculation of `_secondaryReserveRatio` can be overflowed
   9. [M] NibblVault buyout duration longer than update timelock
  10. [M] Reentrancy bug in Basket's withdraw multiple tokens function which gives attacker ability to transfer basket o
  11. [M] Twav._getTwav() will return a wrong result when twavObservationsTWAV_BLOCK_NUMBERS - 1.timestamp = 0.
  12. [M] Basket NFT have no name and symbol

## 2024-07-optimism  (`ee25ec7abd40`) — have 7 / canonical 16  → **+9 missing**
   1. [H] Invalid `DISPUTED_L2_BLOCK_NUMBER` is passed to VM
   2. [H] The LPP challenge period can cause malicious and freeloader claims to be uncounterable and can also cause free
   3. [H] LPP metadata can be altered after the challenge period is over, allowing incorrect states to be proven
   4. [H] L2 precompile calls can be impossible to reproduce on L1
   5. [H] An attacker can bypass the challenge period during LPP finalization
   6. [M] Multiplication overflow leading to memory corruption and incorrect register write-back
   7. [M] Missing address check for instructions LH and LHU
   8. [M] Addresses can be pre-populated with bad data
   9. [M] Unvalidated memory access in `readMem` and `writeMem` functions
  10. [M] Panic in MIPS VM could lead to unchallengeable L2 output root claim
  11. [M] In some cases, proper `CLOCK_EXTENTSION` time cannot be ensured to generate the initial instruction trace
  12. [M] `MIPS` - Incorrect implementation of SRAV instruction
  13. [M] The LPP proposer may not be reimbursed their gas costs by the bonds at `MAX_GAME_DEPTH` because `step()` does 
  14. [M] Honest party's move could become invalid when re-org takes place
  15. [M] The `MIPS` doesn't implement `ADD`, `ADDI`, and `SUB` instructions correctly
  16. [M] Attacker can continuously create games for not yet safe l2 blocks to prevent the update of anchor state

## 2022-04-jpegd  (`e169bbefc6e2`) — have 12 / canonical 20  → **+8 missing**
   1. [H] yVault: First depositor can break minting of shares
   2. [H] Existing user’s locked JPEG could be overwritten by new user, causing permanent loss of JPEG funds
   3. [H] Update initializer modifier to prevent reentrancy during initialization
   4. [H] Reentrancy issue in `yVault.deposit`
   5. [H] `yVaultLPFarming`: No guarantee JPEG currentBalance > previousBalance
   6. [H] Setting new controller can break `YVaultLPFarming`
   7. [H] Controller: Strategy migration will fail
   8. [H] `StrategyPUSDConvex.balanceOfJPEG` uses incorrect function signature while calling `extraReward.earned`, causi
   9. [H] Bad debts should not continue to accrue interest
  10. [M] When _lpToken is jpeg, reward calculation is incorrect
  11. [M] NFTHelper Contract Allows Owner to Burn NFTs
  12. [M] reward will be locked in the farm if no LP join the pool at epoch.startBlock
  13. [M] `setDebtInterestApr` should accrue debt first
  14. [M] Rewards will be locked if user transfer directly to pool without using deposit function
  15. [M] Oracle data feed is insufficiently validated.
  16. [M] Wrong calculation for `yVault` price per share if decimals != 18
  17. [M] `_swapUniswapV2` may use an improper `path` which can cause a loss of the majority of the rewardTokens
  18. [M] The noContract modifier does not work as expected.
  19. [M] Chainlink pricer is using a deprecated API
  20. [M] Division before Multiplication May Result In No Interest Being Accrued

## 2023-08-dopex  (`fa1836e0615e`) — have 23 / canonical 29  → **+6 missing**
   1. [H] Improper precision of strike price calculation can result in broken protocol
   2. [H] Put settlement can be anticipated and lead to user losses and bonding DoS
   3. [H] The settle feature will be broken if attacker arbitrarily transfer collateral tokens to the PerpetualAtlanticV
   4. [H] `UniV3LiquidityAMO::recoverERC721` will cause `ERC721` tokens to be permanently locked in `rdpxV2Core`
   5. [H] Users can get immediate profit when deposit and redeem in `PerpetualAtlanticVaultLP`
   6. [H] Bond operations will always revert at certain time when `putOptionsRequired` is true
   7. [H] Incorrect precision assumed from RdpxPriceOracle creates multiple issues related to value inflation/deflation
   8. [H] The peg stability module can be compromised by forcing lowerDepeg to revert
   9. [H] `ReLPContract` wrongfully assumes protocol owns all of the liquidity in the UniswapV2 pool
  10. [M] Bonding WETH discounts can drain WETH reserves of RdpxV2Core contract to zero
  11. [M] The vault allows "free" swaps from WETH to RDPX
  12. [M] No mechanism to settle out-of-money put options even after Bond receipt token is redeemed.
  13. [M] reLP() mintokenAAmount the calculations are wrong
  14. [M] \_curveSwap: getDpxEthPrice and getEthPrice is in wrong order
  15. [M] Missing slippage parameter on Uniswap `addLiquidity()` function
  16. [M] The owner of RPDX Decaying Bonds is not updated on token transfers
  17. [M] `reLPContract.reLP()` is susceptible to sandwich attack due to user control over `bond()`
  18. [M] A malicious early depositor can manipulate the `LP-Token` price per share to take an unfair share of future us
  19. [M] Change of `fundingDuration` causes "time travel" of `PerpetualAtlanticVault.nextFundingPaymentTimestamp()`
  20. [M] User that delegate eth to `RdpxV2Core` will incur loss if his delegated eth fulfilled by decaying bonds
  21. [M] User can avoid paying high premium price by correctly timing his bond call
  22. [M] Cannot withdraw RDPX if WETH withdrawn is zero
  23. [M] No slippage protection for bonders
  24. [M] `sync` function in `RdpxV2Core.sol` should be called in multiple scenarios to account for the balance changes 
  25. [M] Inaccurate swap amount calculation in ReLP leads to stuck tokens and lost liquidity
  26. [M] The RdpxV2Core contract allows anyone to call redeem tokens even if the contract is paused
  27. [M] Return values of `approve()` not checked
  28. [M] Using `block.timestamp` as the deadline/expiry invites MEV
  29. [M] Unsafe use of `transfer()`/`transferFrom()` with `IERC20`

## 2022-05-cudos  (`2c5e13b4e147`) — have 3 / canonical 6  → **+3 missing**
   1. [M] Missing check in the `updateValset` function
   2. [M] Admin drains all ERC based user funds using `withdrawERC20()`
   3. [M] The `Gravity.sol` should have pause/unpause functionality
   4. [M] Protocol doesn't handle fee on transfer tokens
   5. [M] Calls inside loops that may address DoS
   6. [M] Non-Cudos Erc20 funds sent through `sendToCosmos()` will be lost.

## 2022-11-non-fungible  (`804fe35b0164`) — have 2 / canonical 5  → **+3 missing**
   1. [H] Direct theft of buyer’s ETH funds
   2. [M] Yul `call` return value not checked
   3. [M] Hacked owner or malicious owner can immediately steal all assets on the platform
   4. [M] All orders which use `expirationTime == 0` to support oracle cancellation are not executable
   5. [M] Pool designed to be upgradeable but does not set owner, making it un-upgradeable

## 2021-06-gro  (`e6e43dfea59f`) — have 7 / canonical 10  → **+3 missing**
   1. [H] implicit underflows
   2. [H] `Buoy3Pool.safetyCheck` is not precise and has some assumptions
   3. [H] Incorrect use of operator leads to arbitrary minting of GVT tokens
   4. [H] `sortVaultsByDelta` doesn't work as expected
   5. [M] Usage of deprecated ChainLink API in `Buoy3Pool`
   6. [M] Safe addresses can only be added but not removed
   7. [M] `BaseVaultAdaptor` assumes `sharePrice` is always in underlying decimals
   8. [M] Flash loan risk mitigation is optional and not robust enough
   9. [M] Use of deprecated Chainlink function `latestAnswer`
  10. [M] Early user can break minting

## 2022-05-aura  (`9cc1dc4ae06a`) — have 21 / canonical 23  → **+2 missing**
   1. [H] User can forfeit other user rewards
   2. [M] `BaseRewardPool4626` is not IERC4626 compliant
   3. [M] `CrvDepositorWrapper.sol` relies on oracle that isn't frequently updated
   4. [M] Improperly Skewed Governance Mechanism
   5. [M] `AuraLocker` kick reward only takes last locked amount into consideration, instead of whole balance
   6. [M] Users can grief reward distribution
   7. [M] Rewards distribution can be delayed/never distributed on `AuraLocker.sol#L848`
   8. [M] Reward may be locked forever if user doesn't claim reward for a very long time such that too many epochs have 
   9. [M] Locking up AURA Token does not increase voting power of individual
  10. [M] Reward can be vested even after endTime
  11. [M] Increase voting power by tokenizing the address that locks the token
  12. [M] Users may lose rewards to other users if rewards are given as fee-on-transfer tokens
  13. [M] User will lose funds
  14. [M] `ConvexMasterChef`: When `_lpToken` is cvx, reward calculation is incorrect
  15. [M] Integer overflow will lock all rewards in `AuraLocker`
  16. [M] `ConvexMasterChef`: `safeRewardTransfer` can cause loss of funds
  17. [M] DDOS in `BalLiquidityProvider`
  18. [M] `ConvexMasterChef`'s deposit and withdraw can be reentered drawing all reward funds from the contract if rewar
  19. [M] `AuraBalRewardPool` charges a penalty to all users in the pool if the `AuraLocker` has been shut down
  20. [M] `CrvDepositor.sol` Wrong implementation of the 2-week buffer for lock
  21. [M] `massUpdatePools()` is susceptible to DoS with block gas limit
  22. [M] `ConvexMasterChef`: When using `add()` and `set()`, it should always call `massUpdatePools()` to update all po
  23. [M] Duplicate LP token could lead to incorrect reward distribution

## 2022-05-runes  (`c20104cb90d7`) — have 4 / canonical 6  → **+2 missing**
   1. [M] IERC20.transfer does not support all ERC20 token
   2. [M] Contract may not have enough fund to cover refund
   3. [M] Critical variables shouldn't be changed after they are set
   4. [M] Many unbounded and under-constrained variables in the system can lead to unfair price or DoS
   5. [M] Use of `.send()` May Revert if The Recipient's Fallback Function Consumes More Than 2300 Gas
   6. [M] The owner can mint all of the NFTs.

## 2022-11-stakehouse  (`099243e83259`) — have 51 / canonical 52  → **+1 missing**
   1. [H] Any user being the first to claim rewards from `GiantMevAndFeesPool` can unexepectedly collect them all
   2. [H] Rewards of `GiantMevAndFeesPool` can be locked for all users
   3. [H] Theft of ETH of free floating SLOT holders
   4. [H] Unstaking does not update the mapping `sETHUserClaimForKnot`
   5. [H] Reentrancy in `LiquidStakingManager.sol#withdrawETHForKnow` leads to loss of fund from smart wallet
   6. [H] `BringUnusedETHBackIntoGiantPool` can cause stuck ether funds in Giant Pool
   7. [H] GiantLP with a `transferHookProcessor` cant be burned, users' funds will be stuck in the Giant Pool
   8. [H] function `withdrawETH` from `GiantMevAndFeesPool` can steal most of eth because of idleETH is reduced before b
   9. [H] Incorrect accounting in `SyndicateRewardsProcessor` results in any LP token holder being able to steal other L
  10. [H] `GiantMevAndFeesPool.bringUnusedETHBackIntoGiantPool` function loses the addition of the idleETH which allows 
  11. [H] Protocol insolvent - Permanent freeze of funds
  12. [H] Sender transferring `GiantMevAndFeesPool` tokens can afterward experience pool DOS and orphaning of future rew
  13. [H] Possible reentrancy and fund theft in `withdrawDETH()` of `GiantSavETHVaultPool` because there is no whitelist
  14. [H] Fund lose in function `bringUnusedETHBackIntoGiantPool()` of `GiantSavETHVaultPool` ETH gets back to giant poo
  15. [H] User loses remaining rewards in `GiantMevAndFeesPool` when new deposits happen because `_onDepositETH()` set `
  16. [H] Reentrancy vulnerability in GiantMevAndFeesPool.withdrawETH
  17. [H] Giant pools can be drained due to weak vault authenticity check
  18. [H] Old stakers can steal deposits of new stakers in `StakingFundsVault`
  19. [H] `withdrawETH()` in GiantPoolBase don't call `_distributeETHRewardsToUserForToken()` or `_onWithdraw()` which w
  20. [H] Possibly reentrancy attacks in `_distributeETHRewardsToUserForToken` function
  21. [H] `bringUnusedETHBackIntoGiantPool` in `GiantMevAndFeesPool` can be used to steal `LPTokens`
  22. [M] Freezing of funds - Hacker can prevent users withdraws in giant pools
  23. [M] Rotating `LPTokens` to banned BLS public key
  24. [M] Giant pools cannot receive ETH from vaults
  25. [M] GiantPool should not check ETH amount on withdrawal
  26. [M] Adding non EOA representative
  27. [M] Withdrawing wrong LPToken from GiantPool leads to loss of funds
  28. [M] OwnableSmartWallet: Multiple approvals can lead to unwanted ownership transfers
  29. [M] DAO admin in `LiquidStakingManager.sol` can rug the registered node operator by stealing their fund in the sma
  30. [M] DAO or lsdn owner can steal funds from node runner
  31. [M] Incorrect implementation of the `ETHPoolLPFactory.sol#rotateLPTokens` let user stakes ETH more than `maxStakin
  32. [M] Banned BLS public keys can still be registered
  33. [M] Attacker can grift syndicate staking by staking a small amount
  34. [M] GiantPool `batchRotateLPTokens` function: Minimum balance for rotating LP Tokens should by dynamically calcula
  35. [M] Cross-chain replay attacks are possible with `deployLPToken`
  36. [M] `GiantMevAndFeesPool.previewAccumulatedETH` function: "accumulated" variable is not updated correctly in for l
  37. [M] dETH / ETH / LPTokenETH can become depegged due to ETH 2.0 reward slashing
  38. [M] `Address.isContract()` is not a reliable way of checking if the input is an EOA
  39. [M] Node runners can lose all their stake rewards due to how the DAO commissions can be set to a 100%
  40. [M] When users transfer GiantLP, some rewards may be lost
  41. [M] smartWallet address is not guaranteed correct. ETH may be lost
  42. [M] EIP1559 rewards received by syndicate during the period when it has no registered knots can be lost
  43. [M] ETH sent when calling `executeAsSmartWallet` function can be lost
  44. [M] Calling `updateNodeRunnerWhitelistStatus` function always reverts
  45. [M] Node runner who is already known to be malicious cannot be banned before corresponding smart wallet is created
  46. [M] Incorrect checking in `_assertUserHasEnoughGiantLPToClaimVaultLP`
  47. [M] Compromised or malicious DAO can restrict actions of node runners who are not malicious
  48. [M] `rotateNodeRunnerOfSmartWallet` is vulnerable to a frontrun attack
  49. [M] Funds are not claimed from syndicate for valid BLS keys of first key is invalid (no longer part of syndicate).
  50. [M] User receives less rewards than they are eligible for if first passed BLS key is inactive
  51. [M] Giant pools are prone to user griefing, preventing their holdings from being staked
  52. [M] Vaults can be griefed to not be able to be used for deposits

## 2022-06-notional-coop  (`7b5e1803022e`) — have 10 / canonical 11  → **+1 missing**
   1. [H] Rounding Issues In Certain Functions
   2. [M] fCash of the wrong maturity and asset can be sent to wrapper address before wrapper is deployed
   3. [M] deposit() and mint() and _redeemInternal() in wfCashERC4626() will revert for all fcash that asset token is un
   4. [M] The logic of _isUnderlying() in NotionalTradeModule is wrong which will cause mintFCashPosition() and redeemFC
   5. [M] `IsWrappedFcash` check is a gas bomb
   6. [M] transferfCash does not work as expected
   7. [M] Users Might Not Be Able To Purchase Or Redeem SetToken
   8. [M] Residual Allowance Might Allow Tokens In SetToken To Be Stolen
   9. [M] DOS set token through erc777 hook
  10. [M] Silent overflow of `_fCashAmount`
  11. [M] User can alter amount returned by redeem function due to control transfer

## 2021-07-sherlock  (`97843b77b287`) — have 5 / canonical 6  → **+1 missing**
   1. [H] Single under-funded protocol can break paying off debt
   2. [H] Bug A critical bug in `bps` function
   3. [M] Incorrect internal balance bookkeeping
   4. [M] `_doSherX` optimistically assumes premiums will be paid
   5. [M] reputation risks with `updateSolution`
   6. [M] Yield distribution after large payout seems unfair

## 2021-06-gro  (`9befb133ee74`) — have 9 / canonical 10  → **+1 missing**
   1. [H] implicit underflows
   2. [H] `Buoy3Pool.safetyCheck` is not precise and has some assumptions
   3. [H] Incorrect use of operator leads to arbitrary minting of GVT tokens
   4. [H] `sortVaultsByDelta` doesn't work as expected
   5. [M] Usage of deprecated ChainLink API in `Buoy3Pool`
   6. [M] Safe addresses can only be added but not removed
   7. [M] `BaseVaultAdaptor` assumes `sharePrice` is always in underlying decimals
   8. [M] Flash loan risk mitigation is optional and not robust enough
   9. [M] Use of deprecated Chainlink function `latestAnswer`
  10. [M] Early user can break minting

## 2022-04-xtribe  (`afa60bc8003d`) — have 6 / canonical 7  → **+1 missing**
   1. [M] `xERC4626.sol` Some users may not be able to withdraw until `rewardsCycleEnd` the due to underflow in `beforeW
   2. [M] First xERC4626 deposit exploit can break share calculation
   3. [M] `ERC20Gauges`: The `_incrementGaugeWeight` function does not check the gauge parameter enough, so the user may
   4. [M] In `ERC20Gauges`, contribution to total weight is double-counted when `incrementGauge` is called before `addGa
   5. [M] `FlywheelCore`'s `setFlywheelRewards` can remove access to reward funds from current users
   6. [M] `FlywheelCore.setBooster()` can be used to steal unclaimed rewards
   7. [M] Incorrect accounting of free weight in `_decrementWeightUntilFree`

## 2022-07-swivel  (`b2a8c124d062`) — have 12 / canonical 13  → **+1 missing**
   1. [H] Mismatch in `withdraw()` between Yearn and other protocols can prevent Users from redeeming zcTokens and perma
   2. [M] With most functions in VaultTracker.sol, users can call them only once after maturity has been reached.
   3. [M] Swivel.setFee() is implemented wrongly.
   4. [M] Error in allowance logic
   5. [M] VaultTracker miscalculates compounding interest
   6. [M] Should use >= instead of >
   7. [M] Yearn vault integration is broken
   8. [M] ERC20 Incorrect check on returnedAddress in permit() results in unlimited approval of zero address
   9. [M] ZcToken.withdraw will send user 0 tokens if called after maturity deadline but before market is set mature
  10. [M] VaultTracker has the wrong admin
  11. [M] unpaused(p) modifier missing in authRedeem function
  12. [M] Loss of funds in an underlying protocol would cause catostrophic loss of funds for swivel
  13. [M] Interface definition error

## 2021-12-defiprotocol  (`b7fc4d82013a`) — have 11 / canonical 12  → **+1 missing**
   1. [H] Wrong fee calculation after `totalSupply` was 0
   2. [M] Missing cap on `LicenseFee`
   3. [M] Publisher can lock all user funds in the `Basket` in order to force a user to have their bond burned
   4. [M] `Basket.sol#auctionBurn` calculates `ibRatio` wrong
   5. [M] Reentrancy vulnerability in `Basket` contract's `initialize()` method.
   6. [M] Change in `auctionMultiplier/auctionDecrement` change profitability of auctions and factory can steal all toke
   7. [M] Basket can be fully drained if the auction is settled within a specific block
   8. [M] `Auction.sol#settleAuction()` Bonder may not be able to settle a bonded auction, leading to loss of funds
   9. [M] Lost fees due to precision loss in fees calculation
  10. [M] `Basket:handleFees` fee calculation is wrong
  11. [M] Fee calculation is slightly off
  12. [M] `Basket:handleFees():` fees are overcharged

## Repos with no cached canonical report (need report fetched to assess gap)
  - (unmapped) (`103f39b0f29b`) — v11 has 1 rows
  - (unmapped) (`1167ec3a176e`) — v11 has 7 rows
  - (unmapped) (`27c6f2a68058`) — v11 has 1 rows
  - (unmapped) (`348856fe60ac`) — v11 has 1 rows
  - 2025-04-virtuals-protocol (`51c6dc5fd57f`) — v11 has 3 rows
  - (unmapped) (`592eed5791df`) — v11 has 1 rows
  - (unmapped) (`73f6a793d916`) — v11 has 1 rows
  - (unmapped) (`9470d2cf198f`) — v11 has 2 rows
  - (unmapped) (`9ddd6b83c27e`) — v11 has 8 rows
  - (unmapped) (`a4d91fb1550f`) — v11 has 2 rows
  - (unmapped) (`c2426a2ab283`) — v11 has 1 rows
  - (unmapped) (`e7921851ec01`) — v11 has 1 rows
