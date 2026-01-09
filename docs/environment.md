# Local Environment Requirements

## System Requirements

- **Docker:** >= 20.x
- **Docker Compose:** >= 2.x
- **CPU:** 4 cores
- **RAM:** 8–16 GB
- **Disk:** >= 20 GB free space

---

## Networking

- All services run on a single Docker network:
  - `space_net`

---

## Database Access

To connect to the Postgres data warehouse (`space_warehouse`), use:

```bash
psql -h postgres -U space_user -d space_warehouse
