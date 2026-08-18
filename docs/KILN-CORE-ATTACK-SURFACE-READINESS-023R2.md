# Kiln Core Attack-Surface Readiness 023R2

Core 023R2 supersedes the previous surface-readiness implementation.

Pressure contracts own attack-surface identity.

Coupling contracts are associated with surfaces through pressure_contract_id.

Kiln must not assume duplicated attack_surface metadata exists on coupling contracts.

PROVEN requires a completed bounded campaign.

CONTRACT_ONLY requires at least one pressure contract with a corresponding coupling contract.

Only CONTRACT_ONLY surfaces may enter injector discovery.
