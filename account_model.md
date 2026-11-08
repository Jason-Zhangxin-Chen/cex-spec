# Account Model

The data model for an account on a centralized exchange (CEX) is hierarchical and multi-dimensional. It doesn't store a single "balance" number; instead, it breaks down holdings by wallet type, asset, and balance status (available, locked, margin, etc.). This structure is necessary to support spot trading, margin, derivatives, and fiat operations simultaneously.

Here is a breakdown of how such an account is typically modeled.

## The Hierarchical Structure: Account -> Wallet > Asset > Balance
A single user Account (identified by a unique accountId) is not a monolithic pool of funds. It is a container for multiple sub-accounts or wallets, each serving a distinct function.

Level	Entity	Description	Key Fields (Examples)
1. Account	Account	The root identity.	accountId, accountType (e.g., SPOT, MARGIN, FUTURES), updateTime
2. Wallet	Wallet / Sub-Account	Isolates funds by product line (Spot, Cross Margin, USDⓈ-M Futures, COIN-M Futures, Funding, Earn).	walletType, walletBalance (aggregate)
3. Asset Balance	AssetBalance / AccountAsset	The per-asset holding record within a specific wallet.	asset (BTC, ETH, USDT), free, locked, borrowed, interest

Why the separation? Exchanges isolate wallets (e.g., Spot vs. Futures) for risk management and system architecture. A failure or anomaly in the Futures engine should not directly impact the Spot wallet.

## The Multi-Dimensional Balance of a Single Asset
For any given asset (e.g., USDT) within a specific wallet, the model stores several distinct balance dimensions rather than a single number.

1. free / availableBalance
The quantity of the asset that is immediately usable for new orders, withdrawals, or transfers.

In Binance's API, this is often represented as free (Spot) or availableBalance (Futures/Margin).

Formula (simplified): Available = Total Wallet Balance - Locked - Margin Collateral - Unrealized Losses (for derivatives).

2. locked / reserved
Funds that are reserved and unavailable because they are committed elsewhere.

Open Orders: The unfilled portion of limit orders on the order book.

Margin Collateral: Funds pledged to support an open leveraged position.

Earn/Staking: Assets subscribed to yield-generating products that are not yet redeemed.

In models like Lighter's AccountAsset, this is explicitly called locked_balance.

3. totalWalletBalance / balance
The gross quantity of the asset held in that specific wallet, before subtracting locked amounts or adding/subtracting unrealized PnL.

Binance's Portfolio Margin API defines totalWalletBalance as an aggregate figure for a given asset across certain wallet types.

4. marginBalance (Derivatives & Margin)
A dynamic measure used in leveraged trading, representing the effective equity supporting positions.

Formula (Futures): Margin Balance = Wallet Balance + Unrealized PnL.

In the Lighter AccountAsset model, margin_balance is a distinct field from balance and locked_balance.

For Cross Margin, the model extends further with fields like crossMarginFree, crossMarginLocked, crossMarginBorrowed, and crossMarginInterest.

5. borrowed & interest (Margin-Specific)
For margin trading, the balance model explicitly tracks debt.

borrowed: The amount of the asset owed to the exchange/lender.

interest: Accrued interest on the borrowed amount.

Binance's MarginBalance GraphQL type extends AssetBalance with these exact fields.

6. unrealizedPNL
For derivatives wallets (USDⓈ-M and COIN-M), the account asset record includes umUnrealizedPNL and cmUnrealizedPNL, which directly modify the marginBalance.

## How Fiat (USD) Fits In
Fiat currencies (e.g., USD) are modeled as just another asset within the system. A user's USD holding in their Spot or Funding wallet would be represented as an AssetBalance where asset = "USD". It possesses the same dimensions (free, locked) as a crypto asset. The only distinction is in the deposit/withdrawal rails (bank transfer vs. blockchain), not in the core balance data model.

## A Conceptual Schema
```text
Account
  - account_id (PK)
  - user_id
  - account_type (SPOT, MARGIN, FUTURES, etc.)
  - status
  - update_time

AssetBalance  (PK: account_id + wallet_type + asset)
  - account_id (FK)
  - wallet_type (e.g., SPOT, CROSS_MARGIN, UM_FUTURES)
  - asset (e.g., BTC, USDT, USD)
  - total_balance          // Gross wallet balance
  - available_balance      // Free for new orders/withdrawals
  - locked_balance         // Reserved for open orders, collateral
  - borrowed               // Margin debt (0 if not applicable)
  - interest               // Accrued margin interest
  - unrealized_pnl         // For derivatives wallets
  - margin_balance         // Wallet + unrealized PnL (derivatives)
```
Key takeaway: The model is designed to answer not just "how much does the user have?" but precisely "how much can they use right now, and how much is already committed?" across every product vertical and asset type simultaneously.

## Model in Rust
```rust
use chrono::{DateTime, Utc};
use rust_decimal::Decimal;
use rust_decimal_macros::dec;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use thiserror::Error;

// ───────────────────────────── IDs & newtypes ─────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct AccountId(pub u64);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct UserId(pub u64);

/// Asset ticker, normalized to uppercase. Newtype so a `Symbol` (BTCUSDT)
/// can never be passed where an `Asset` (BTC) is expected.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct Asset(String);

impl Asset {
    pub fn new(s: impl Into<String>) -> Self {
        Asset(s.into().trim().to_uppercase())
    }
    pub fn as_str(&self) -> &str {
        &self.0
    }
}
impl From<&str> for Asset {
    fn from(s: &str) -> Self {
        Self::new(s)
    }
}

// ───────────────────────────── Enums ─────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum AccountType {
    Standard,
    PortfolioMargin,
    SubAccount,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum AccountStatus {
    Active,
    Frozen,
    Closed,
}

/// Part of the primary key of a balance row. `IsolatedMargin(pair_id)`
/// gives each isolated pair its own virtual wallet.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum WalletType {
    Spot,
    CrossMargin,
    IsolatedMargin(u32), // symbol/pair id
    UsdMFutures,
    CoinMFutures,
    Funding,
    Earn,
}

impl WalletType {
    pub fn is_margin(self) -> bool {
        matches!(self, Self::CrossMargin | Self::IsolatedMargin(_))
    }
    pub fn is_derivatives(self) -> bool {
        matches!(self, Self::UsdMFutures | Self::CoinMFutures)
    }
    /// Only derivatives wallets carry unrealized PnL into margin balance.
    pub fn has_pnl(self) -> bool {
        self.is_derivatives()
    }
}

// ───────────────────────────── Errors ─────────────────────────────

#[derive(Debug, Error, PartialEq)]
pub enum BalanceError {
    #[error("amount must be positive, got {0}")]
    NonPositiveAmount(Decimal),
    #[error("insufficient available balance: need {need}, have {have}")]
    InsufficientAvailable { need: Decimal, have: Decimal },
    #[error("invariant violated: {0}")]
    Invariant(String),
}

// ───────────────────────────── AssetBalance ─────────────────────────────

/// Canonical row. Primary key: (account_id, wallet_type, asset).
/// Maps 1:1 to a DB table; product-specific fields default to 0.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AssetBalance {
    pub account_id: AccountId,
    pub wallet_type: WalletType,
    pub asset: Asset,

    /// Gross holdings in this wallet (before debt, includes locked).
    pub total: Decimal,
    /// Immediately usable for orders / withdrawals / transfers.
    pub available: Decimal,
    /// Reserved: open orders, collateral, staking locks.
    pub locked: Decimal,

    // Margin-only (0 elsewhere)
    #[serde(default)]
    pub borrowed: Decimal,
    #[serde(default)]
    pub interest: Decimal,

    // Derivatives-only (0 elsewhere)
    #[serde(default)]
    pub unrealized_pnl: Decimal,

    pub updated_at: DateTime<Utc>,
}

impl AssetBalance {
    // ── Constructors per product line ──

    pub fn spot(account_id: AccountId, asset: impl Into<Asset>, amount: Decimal) -> Self {
        Self {
            account_id,
            wallet_type: WalletType::Spot,
            asset: asset.into(),
            total: amount,
            available: amount,
            locked: Decimal::ZERO,
            borrowed: Decimal::ZERO,
            interest: Decimal::ZERO,
            unrealized_pnl: Decimal::ZERO,
            updated_at: Utc::now(),
        }
    }

    pub fn margin(
        account_id: AccountId,
        wallet_type: WalletType,
        asset: impl Into<Asset>,
        total: Decimal,
        borrowed: Decimal,
        interest: Decimal,
    ) -> Self {
        debug_assert!(wallet_type.is_margin());
        Self {
            account_id,
            wallet_type,
            asset: asset.into(),
            total,
            available: total - borrowed - interest, // may be negative → margin call
            locked: Decimal::ZERO,
            borrowed,
            interest,
            unrealized_pnl: Decimal::ZERO,
            updated_at: Utc::now(),
        }
    }

    pub fn derivative(
        account_id: AccountId,
        wallet_type: WalletType,
        asset: impl Into<Asset>,
        wallet_balance: Decimal,
        unrealized_pnl: Decimal,
    ) -> Self {
        debug_assert!(wallet_type.has_pnl());
        Self {
            account_id,
            wallet_type,
            asset: asset.into(),
            total: wallet_balance,
            available: wallet_balance,
            locked: Decimal::ZERO,
            borrowed: Decimal::ZERO,
            interest: Decimal::ZERO,
            unrealized_pnl,
            updated_at: Utc::now(),
        }
    }

    // ── Derived figures (never stored, always computed) ──

    /// Wallet balance + unrealized PnL. For derivatives this is the number
    /// that liquidation engines care about; for spot it is just `total`.
    pub fn margin_balance(&self) -> Decimal {
        if self.wallet_type.has_pnl() {
            self.total + self.unrealized_pnl
        } else {
            self.total
        }
    }

    /// True net equity after debt and interest.
    pub fn equity(&self) -> Decimal {
        self.total + self.unrealized_pnl - self.borrowed - self.interest
    }

    pub fn is_negative(&self) -> bool {
        self.equity().is_sign_negative()
    }

    // ── Mutations (the only sanctioned way to move money) ──

    pub fn lock(&mut self, amount: Decimal) -> Result<(), BalanceError> {
        if amount <= Decimal::ZERO {
            return Err(BalanceError::NonPositiveAmount(amount));
        }
        if amount > self.available {
            return Err(BalanceError::InsufficientAvailable {
                need: amount,
                have: self.available,
            });
        }
        self.available -= amount;
        self.locked += amount;
        self.updated_at = Utc::now();
        Ok(())
    }

    pub fn unlock(&mut self, amount: Decimal) -> Result<(), BalanceError> {
        if amount <= Decimal::ZERO {
            return Err(BalanceError::NonPositiveAmount(amount));
        }
        if amount > self.locked {
            return Err(BalanceError::Invariant(format!(
                "unlock {} > locked {}",
                amount, self.locked
            )));
        }
        self.locked -= amount;
        self.available += amount;
        self.updated_at = Utc::now();
        Ok(())
    }

    /// Settle a fill: consume locked funds and remove them from the wallet.
    pub fn settle(&mut self, amount: Decimal) -> Result<(), BalanceError> {
        if amount <= Decimal::ZERO {
            return Err(BalanceError::NonPositiveAmount(amount));
        }
        if amount > self.locked {
            return Err(BalanceError::Invariant(format!(
                "settle {} > locked {}",
                amount, self.locked
            )));
        }
        self.locked -= amount;
        self.total -= amount;
        self.updated_at = Utc::now();
        Ok(())
    }

    // ── Invariants (call on write, and in a periodic consistency job) ──

    pub fn validate(&self) -> Result<(), BalanceError> {
        const EPS: Decimal = dec!(0.00000001);

        for (name, v) in [
            ("total", self.total),
            ("available", self.available),
            ("locked", self.locked),
            ("borrowed", self.borrowed),
            ("interest", self.interest),
        ] {
            if v.is_sign_negative() && !(name == "available" && self.wallet_type.is_margin()) {
                return Err(BalanceError::Invariant(format!("{name} is negative: {v}")));
            }
        }
        if self.available + self.locked > self.total + EPS {
            return Err(BalanceError::Invariant(format!(
                "available {} + locked {} > total {}",
                self.available, self.locked, self.total
            )));
        }
        if (self.borrowed != Decimal::ZERO || self.interest != Decimal::ZERO)
            && !self.wallet_type.is_margin()
        {
            return Err(BalanceError::Invariant(
                "debt fields set on non-margin wallet".into(),
            ));
        }
        if self.unrealized_pnl != Decimal::ZERO && !self.wallet_type.has_pnl() {
            return Err(BalanceError::Invariant(
                "unrealized_pnl set on non-derivatives wallet".into(),
            ));
        }
        Ok(())
    }
}

// ───────────────────────────── Wallet & Account ─────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Wallet {
    pub wallet_type: WalletType,
    pub balances: HashMap<Asset, AssetBalance>,
}

impl Wallet {
    pub fn new(wallet_type: WalletType) -> Self {
        Self { wallet_type, balances: HashMap::new() }
    }

    pub fn balance(&self, asset: &Asset) -> Option<&AssetBalance> {
        self.balances.get(asset)
    }

    pub fn available(&self, asset: &Asset) -> Decimal {
        self.balances.get(asset).map(|b| b.available).unwrap_or_default()
    }

    pub fn upsert(&mut self, balance: AssetBalance) -> Result<(), BalanceError> {
        balance.validate()?;
        debug_assert_eq!(balance.wallet_type, self.wallet_type);
        self.balances.insert(balance.asset.clone(), balance);
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Account {
    pub id: AccountId,
    pub user_id: UserId,
    pub account_type: AccountType,
    pub status: AccountStatus,
    pub wallets: HashMap<WalletType, Wallet>,
    pub updated_at: DateTime<Utc>,
}

impl Account {
    pub fn wallet(&self, wallet_type: WalletType) -> Option<&Wallet> {
        self.wallets.get(&wallet_type)
    }

    pub fn balance(&self, wallet_type: WalletType, asset: &Asset) -> Option<&AssetBalance> {
        self.wallets.get(&wallet_type)?.balance(asset)
    }

    /// "How much USDT can the user actually move right now, everywhere?"
    pub fn total_available(&self, asset: &Asset) -> Decimal {
        self.wallets.values().map(|w| w.available(asset)).sum()
    }

    /// Net equity per asset, aggregated across every wallet.
    pub fn total_equity(&self, asset: &Asset) -> Decimal {
        self.wallets
            .values()
            .filter_map(|w| w.balance(asset))
            .map(AssetBalance::equity)
            .sum()
    }

    pub fn validate(&self) -> Result<(), BalanceError> {
        for wallet in self.wallets.values() {
            for balance in wallet.balances.values() {
                if balance.account_id != self.id {
                    return Err(BalanceError::Invariant("balance belongs to another account".into()));
                }
                if balance.wallet_type != wallet.wallet_type {
                    return Err(BalanceError::Invariant("balance filed under wrong wallet".into()));
                }
                balance.validate()?;
            }
        }
        Ok(())
    }
}
```
A few notes worth flagging:

AssetBalance is the DB row, not the source of truth. In a real CEX the authoritative record is an append-only double-entry ledger (LedgerEntry { account_id, wallet_type, asset, delta, ref_id: OrderId|TradeId|TransferId, seq }), and this struct is a materialized snapshot rebuilt from it. That's what makes reconciliation and audit possible; the snapshot exists for O(1) reads on the hot path.

available is the only field allowed to be negative, and only on margin wallets — that's the margin-call signal. Every other field is guarded in validate().

Option<Decimal> vs Decimal::ZERO: I chose flat zeros with validate() rejecting them on the wrong wallet type. This matches how exchanges store rows (nullable-free tables, cheap SUM), while the invariants recover type safety at the boundary.

For persistence, derive sqlx::FromRow on AssetBalance behind a feature flag, and key the table on PRIMARY KEY (account_id, wallet_type, asset); you'll want a covering index on (account_id, asset) for the cross-wallet aggregation queries.

Use rust_decimal with features = ["serde-with-str"] so amounts round-trip as JSON strings and never touch f64.

## Model in Diagram
```text
┌──────────────────────────────────────────────────────────────────────────┐
│ LEVEL 0 — ROOT                                                           │
│                                                                          │
│   Account { id, user_id, account_type, status, updated_at }              │
│     │                                                                    │
│     └── wallets: HashMap<WalletType, Wallet>                             │
│          (1 Account ──► N Wallets — one per product line)                │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ LEVEL 1 — WALLETS  (keyed by WalletType)                                 │
│                                                                          │
│  ┌──────┬─────────────┬──────────────────┬──────────┬──────────┬────────┬──────┐
│  │ Spot │ CrossMargin │ IsolatedMargin(id)│ USDⓈ-M  │ COIN-M   │ Funding│ Earn │
│  └──────┴─────────────┴──────────────────┴──────────┴──────────┴────────┴──────┘
│     │                                                                    │
│     └── balances: HashMap<Asset, AssetBalance>                           │
│          (1 Wallet ──► N Assets — BTC, ETH, USDT, USD, …)                │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ LEVEL 2 — ASSET BALANCES   PK = (account_id, wallet_type, asset)         │
│                                                                          │
│   AssetBalance                                                           │
│   ┌──────────────────────────┬─────────────────┬───────────────────────┐ │
│   │ CORE (all wallets)       │ MARGIN ONLY     │ DERIVATIVES ONLY      │ │
│   ├──────────────────────────┼─────────────────┼───────────────────────┤ │
│   │ total                    │ borrowed        │ unrealized_pnl        │ │
│   │ available                │ interest        │                       │ │
│   │ locked                   │                 │                       │ │
│   └──────────────────────────┴─────────────────┴───────────────────────┘ │
│                                                                          │
│   Derived (computed, never stored):                                      │
│     margin_balance() = total + unrealized_pnl                            │
│     equity()         = total + unrealized_pnl − borrowed − interest      │
└──────────────────────────────────────────────────────────────────────────┘
```
Notice: the same asset (USDT) appears in four different wallets, each with its own independent total / available / locked / borrowed / unrealized_pnl dimensions. That is the whole point of separating wallets — USDT collateral for a futures position is not the same USDT you can spend on spot.

## Relationship summary

Edge	Cardinality	Mechanism	Why
Account → Wallet	1 : N	HashMap<WalletType, Wallet>	Isolate risk per product line (Futures engine failure ≠ Spot loss)
Wallet → AssetBalance	1 : N	HashMap<Asset, AssetBalance>	O(1) lookup on the hot path (acct.wallet(Spot)?.balance(&BTC))
AssetBalance	leaf row	PK = (account_id, wallet_type, asset)	Unique per (account, product, asset) triple
WalletType	closed enum	IsolatedMargin(u32) carries a pair id	Isolated margin needs one virtual wallet per trading pair

Rule of thumb: if you find yourself wanting to move money from one box to another in this tree, that's a double-entry ledger transfer, not a mutation of a single AssetBalance. The tree above is the snapshot; the ledger is the source of truth.

## Which wallet for which job
🧭 Quick reference: which wallet for which job
If the user wants to…	Wallet type	Collateral asset
Trade spot BTC/USDT	Spot	BTC / USDT
Leverage with dollar-denominated PnL	USDⓈ-M Futures	USDT / USDC
Leverage using their BTC as collateral	COIN-M Futures	BTC / ETH
Deposit, withdraw, P2P, or pay with card	Funding (→ Stocks Account)	Crypto / USD settlement currencies
Earn yield on idle assets	Earn	The subscribed asset
