# Local Environment Requirements

- Docker: >= 20.x
- Docker Compose: >= 2.x
- CPU: 4 cores
- RAM: 8–16GB
- Disk: >= 20GB free

All services run on a single Docker network: `space_net`.

Note that you must connect to space_warehouse:
psql -h postgres -U space_user -d space_warehouse
Mention the ingestion image:
Ingestion jobs run in the `space-objects-ingestion` image, defined under `infra/ingestion/Dockerfile`

