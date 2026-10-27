#Spec of the CEX — Multi-Active HA CEX Trade System

##The overview
As a CEX system, it serves trade services in the internet for different regions, thus the user requests are routed into
different CEX clusters hosted by different data center, and there are cross data center (<100km) Raft consensus replications for cross data
center HA. Services within the same data center has local HA replications.

The models that need to be draw in the overview diagram are:

###The user plane traffic comes from
The external user plane traffic comes from below two sources, after the CDN, DDoS and WAF filters, they hit into the
load balancers which should be registered into the cloud providers GTM, with the **traffic routing strategies**. There
 are a cluster of load balancer which is stateless.

 - Clients
 The clients include Web UI, Android, IOS and ZenDesk (customer support system). They collect to the system via Https/WS through the CDN, DDoS and
 WAF filters in the GTM DNS layer.

 - OpenAPI
 This interface provides Spot, Perpetual, Prediction production, and Option trade API for market makers where they have their own strategy trading
 system using the interfaces.

###The control plane traffic comes from
The control plane traffic comes from multiple operation UIs via VPN channel one, they hit into the load balancers which should be
registered into the cloud providers GTM. There are a cluster of load balancer which is stateless.

 - Exchange operation UI
 - Risk control operation UI
 - ClearingHouse operation UI
 - Wallet operation UI
 - Wallet risk control operation UI
 - MPC APP (Signature Risk Control&Approve)

###The monitoring & governance plane traffic comes from
The monitoring & governance plane traffic comes from one source via VPN channel two, they hit into the load balancers
which should be registered into the cloud GTM.
 - Cluster Monitoring UI
 - Cluster Governance UI

###Gateway (NGINX) clusters
The gateway services for traffic volume control, busyness request routing and rate limit. It routes and forwards requests directly into the service clusters; Aeron is used internally between services within the service clusters.

###Service clusters
The service clusters involves multiple types of services: the kernel services, edge services, control plane services,
monitoring&governance services.

####Kernel services
The kernel services are the core engines for the exchange; stateful services among them have state recovery on disaster
cases.

- OMS & Match Engine Clusters
Cover spot, perpetual, prediction and options product lines; every cluster has a master with multi-slaves semi synchronous replication, applying changes from master to local books.

- Clearing Clusters
Position book management and margin accounting for perpetual, prediction and options products; spot trade settlement as internal settlement.

- Risk Monitoring Engine (Event based)
Master with multi-slaves semi synchronous replication (contains the liquidation state machine). Triggered by mark price ticks, fills, funding and transfer events (not polling); tracks the top N candidates for position liquidation, insurance, ADL.

- Risk Governance services
Master with multi-slaves semi synchronous replication (contains the liquidation state machine). Execute position liquidation, insurance and ADL.

- Settlement Clusters
Derivatives settlement triggered periodically (funding fee collection) or by expiry events (option expiry settlement).

- Market data engine clusters
Shared by symbol; aggregate market data and shard them into different shards of the redis cluster, with master and multi-slaves semi synchronous replication for backup.

- C2C/P2P trade services
Provide OTC request for quote trades service. All the state are stored in Redis cluster, and eventually sync to SQL DB.

- User accounting services (Fiat, Crypto assets pooling)
Fiat or Crypto deposit/withdraw, internal ledger for this.

- Wallet service (Web3-blockchain TXN)

- Wallet & wallet risk control services (crypto asset transfer, regulations, anti money cleaning)

- MPC signature gateway

- MPC Actor (SGX) signature services

- KYT (Elliptic)

#### Edge Services
- User management services
User management services.
- AUTH management
Login auth base on jwt.
- Market data (pub/sub) gateway services
- User messaging services
 Email, text message,
- KYC services

#### Operation&Control plane services
 - Operation Configs (Risk Engines, etc...)
 - Position Locking
 - Hong Bao
 - IEO
 - Airdrop
 - YouHuiQuan

#### Monitoring & Governance plane
 - Monitoring & Governance clusters
Service metric monitoring and service health monitoring.

OMS and market data engine slave-master failover is handled by consensus algorithms without manual operation (2026-10-26).

### Data layer clusters
 - Aeron messaging clusters
 - Redis cache clusters (Multiple Instance of Cluster)
 - Market data data center (Redis Cluster Shards)
 - Column data center (Regression Test Market Data)
 - SQL database clusters (Replicate from Redis XStream)
 - Object storage clusters (Archive & Snapshot)
 - TS database (System monitoring metrics)

### External system connectors
 - Public blockchain RPC clusters
 - KYT service providers
 - 3rd party KYC service providers
 - 3rd party wallet agents
 - Fiat money channel agents
### Appendix: approved additions (2026-10-23)

#### Kernel services (additions)
- Index price service (Oracle)
Aggregate external market data to compute the mark price for funding, option settlement and liquidation.
- KMS/HSM key management services
Custody of system keys: JWT signing keys, API keys, etc...

#### Edge Services (additions)
- OpenAPI key management services
API key issuance, signature verification and rate limit for the OpenAPI market makers.

#### Operation&Control plane services (additions)
- Audit log services
Audit trail of operations, written to object storage.
- Regulatory report services
Regulatory reporting (suspicious transaction reports, etc...).
- Scheduled job services
Unified cron scheduling (funding settlement, snapshots, campaign draws, etc...).
- Reconciliation services
Reconciliation of clearing, wallet and fiat channels.

#### Control plane traffic sources (additions)
- C2C merchant management UI

#### External system connectors (additions)
- Index price data sources
Market data feeds from multiple exchanges for index price.

#### Description updates
- Clearing&Settlement Services: split into Clearing Clusters and Settlement Clusters (2026-10-24).
- ES data services: also aggregate application logs.
- User messaging services: email, text message and App push notifications.

#### Kernel services (additions, 2026-10-26)

- AI trading clusters
Run AI trader inference on top of the current market data and order books; traders delegate their accounts to the AI trader clusters, they pay the fee to the CEX and the CEX trades for them for higher profit.

- Pretrade clusters (moved from Edge Services)
Every cluster has a master with multi-slaves semi synchronous replication. Stateful: available balance and reserved-funds tables (spot: quote/base lock; futures: initial margin lock), per-account open order count and notional, cached instrument params and risk limits. Reservation is atomic with order acceptance and lives in the same shard as the account. Pretrade clusters stop invalid orders hitting the OMS&MatchEngine; all product lines share the same upstream pretrade clusters.

#### Naming convention (2026-10-23)
All services inside the service clusters are named with the "集群 (Cluster)" suffix, indicating multi-instance HA deployment.

#### Kernel services (additions, 2026-10-26)

- AI trading clusters
Run AI trader inference on top of the current market data and order books; traders delegate their accounts to the AI trader clusters, they pay the fee to the CEX and the CEX trades for them for higher profit.

- Deposit & Withdrawal service clusters (moved from Edge Services)
Withdrawal request management, deposit watching, withdrawal address whitelist and signing orchestration. Flows: deposit&withdrawal -> user accounting (ledger), -> wallet risk control -> KYT, -> wallet service -> public blockchain RPC; fiat withdrawal via fiat money channel agents.

#### Edge Services (additions, 2026-10-26)
- Data reader clusters
All data reading requests go through the data reader clusters (market data, orders, trades, assets, etc...).

- Data reading pipeline (sub-group of Edge Services): contains the data reader clusters and the market data pub/sub gateway clusters (2026-10-26).

#### Kernel services (additions, 2026-10-26)

- AI trading clusters
Run AI trader inference on top of the current market data and order books; traders delegate their accounts to the AI trader clusters, they pay the fee to the CEX and the CEX trades for them for higher profit.

- Wallet service clusters (container): contain wallet risk control, MPC signature gateway, MPC Actor (SGX), KYT and KMS/HSM private key management as sub-systems.

- Naming (2026-10-26): Operation&Control plane services drop the "集群 (Cluster)" suffix as they are not heavy clusters.

#### Kernel services (additions, 2026-10-26)

- AI trading clusters
Run AI trader inference on top of the current market data and order books; traders delegate their accounts to the AI trader clusters, they pay the fee to the CEX and the CEX trades for them for higher profit.

#### Edge Services (additions, 2026-10-26)
- Campaign service clusters
User-facing campaign execution: Hong Bao claiming, IEO subscription, airdrop claiming, coupon usage.

#### Operation&Control plane services (additions, 2026-10-26)
- Fee configs
Tagged with the operation configs (risk engines & fee schedules); fee application happens on the OMS & MatchEngine side.
- Config center
Dynamic service-level configuration delivery.

#### Control plane traffic sources (additions, 2026-10-26)
- Market maker management UI

#### Monitoring & Governance plane (additions, 2026-10-26)
- Match replay service clusters
Replay matching flows based on the regression test market data in the column data center.

#### Flows (additions, 2026-10-26)
- Fiat deposit: fiat money channel agents -> deposit & withdrawal service clusters.

- Trade scheduler gateway clusters (Edge Services, 2026-10-26)
The gateway is aware of the master pretrade nodes; trading commands are routed to the master pretrade nodes.

- Trade scheduling (2026-10-26): both trade scheduler gateway clusters schedule and forward requests by account ID sharding to the downstream pretrade clusters in both data centers; pretrade clusters register their master and slave IPs in the gateways.

#### Kernel services (additions, 2026-10-27)
- Ledger clusters
Single source of truth for ledger data; all ledger data operations go through them.
- Position/Margin clusters
Single source of truth for position and margin data; all position/margin data operations go through them.

- Data archive services and ES data services (moved from Data layer, 2026-10-27)
They are services handling data in the kernel; the data layer keeps only the clusters.
