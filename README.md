# AssistCX Platform Guide

## Version Management

Our project uses Semantic Versioning (SemVer) for version numbering. The version is stored in `backend/__init__.py` and follows the format MAJOR.MINOR.PATCH.

### Viewing the Current Version

To view the current version:

```bash
python backend/version.py
```

### Bumping the Version

To bump the version, use the `build.sh` script with the `--bump` option:

```bash
./scripts/build.sh --bump [major|minor|patch]
```

- `--bump major`: Increments the MAJOR version (e.g., 1.0.0 -> 2.0.0)
- `--bump minor`: Increments the MINOR version (e.g., 1.0.0 -> 1.1.0)
- `--bump patch`: Increments the PATCH version (e.g., 1.0.0 -> 1.0.1)

Example:

```bash
./scripts/build.sh --bump patch
```

This will:

1. Increment the version in `backend/__init__.py`
2. Commit the change
3. Create a new git tag for the version
4. Build Docker images with the new version tag

### Building Without Version Bump

To build using the current version without bumping:

```bash
./scripts/build.sh
```

This will use the version specified in `backend/__init__.py` for tagging Docker images.

### Building with 'latest' Tag

To build and tag images as 'latest':

```bash
./scripts/build.sh --latest
```

### Create and push images to registry

```bash
./scripts/build.sh --push
```

### Additional Build Options

- `--amd`: Build for AMD64 platform
- Combine options: `./scripts/build.sh --bump minor --amd`

### Best Practices

1. Always use `--bump` when releasing a new version.
2. Use `patch` for backwards-compatible bug fixes.
3. Use `minor` for backwards-compatible new features.
4. Use `major` for breaking changes.
5. Coordinate with team members before bumping `major` or `minor` versions.
6. Update the changelog when bumping versions.
7. Push changes and tags to the remote repository after bumping.

For any questions or issues with versioning, please contact the project maintainers.

## Build the images

### Build the containers in MacOS/Linux:

1. Use `./scripts/build.sh` file to build Docker images
2. Set execute permission to build script: `chmod +x ./scripts/build.sh`
3. Create new images with latest tag: `./scripts/build.sh --latest`
4. Bump version and create images: `./scripts/build.sh --bump [major|minor|patch]`
5. Rebuild images with existing version tag: `./scripts/build.sh`
6. Build images for amd64 platform: `./scripts/build.sh --amd`
7. Run the docker containers (Optional): `docker compose up -d`

### Build the containers in Windows:

1. Use `./scripts/build.ps1` file to build Docker images

### Build script arguments.

Use `./scripts/build.sh --help` to see the list of arguments. Multiple arguments can be combined.

```bash
./scripts/build.sh --latest
./scripts/build.sh --bump [major|minor|patch]
./scripts/build.sh --amd
./scripts/build.sh --push
```

## Running the Platform

This platform can be run on both Unix-based systems (MacOS/Linux) and Windows. We provide scripts to simplify the process of starting, stopping, and updating the containers.

### Prerequisites

- Docker and Docker Compose installed on your system
- Git repository cloned to your local machine
- `.env` file properly configured in the root directory of the project

### MacOS/Linux

Use the `start.sh` script located in the `scripts` directory to manage the platform.

1. Set execute permission for the script (if not already set):

   ```
   chmod +x ./scripts/start.sh
   ```

2. To start the platform with the current version:

   ```
   ./scripts/start.sh
   ```

3. To start the platform with the latest images:

   ```
   ./scripts/start.sh --latest
   ```

4. To start the platform with a specific version:

   ```
   ./scripts/start.sh --X.Y.Z
   ```

   Replace X.Y.Z with the desired version number (e.g., --1.2.3)

5. To update all images to the latest version and start the platform:
   ```
   ./scripts/start.sh --update
   ```

On remote server, you can use `start.sh` script to start the platform in staged mode. This will start services in staged manner for better resource utilization. Add `--staged` option to the command to start the services in staged manner.

```
./scripts/start.sh --staged
./scripts/start.sh --update --staged
./scripts/start.sh --latest --staged
./scripts/start.sh --X.Y.Z --staged
```

### Windows

Use the `start.ps1` script located in the `scripts` directory to manage the platform.

1. To start the platform with the current version:

   ```
   .\scripts\start.ps1
   ```

2. To start the platform with the latest images:

   ```
   .\scripts\start.ps1 --latest
   ```

3. To start the platform with a specific version:

   ```
   .\scripts\start.ps1 --X.Y.Z
   ```

   Replace X.Y.Z with the desired version number (e.g., --1.2.3)

4. To update all images to the latest version and start the platform:
   ```
   .\scripts\start.ps1 --update
   ```

### Additional Notes

- If no argument is provided, the script will use the current version of images.
- The `--update` option removes all existing project-related Docker images before pulling the latest versions.
- If a specific version is requested (e.g., --1.2.3), the script will check if the required images for that version exist. If they don't, it will display an error message.
- The scripts automatically handle Docker login using credentials from the `.env` file.
- If services are already running, the scripts will restart them instead of starting new containers.

For any issues or additional configuration needs, please refer to the troubleshooting section or contact the development team.

## Database migration

Contstraints naming convenstion:

```
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
```

In order to generate migration version file, follow these steps

1. Make sure to import the model class in `models/__init__.py`
2. Ensure that the backend-core containers and services are running
3. Create new Alembic migration: `docker compose exec backend-core alembic revision --autogenerate -m "small message"`
4. Squash and rebase migrations: `docker compose exec backend-core alembic revision --autogenerate -m "new baseline"`

In order to commit migratrion, follow these steps

1. Get the list of schemas in the database where you want to apply migration
2. Commit using alembic command: `docker compose exec backend-core alembic -x tenant=[schema] upgrade head`
3. Or commit using migration script: `./migration.sh schema1 schema2 schema3`

To downgrade

1. Downgrade one revision: docker compose exec backend-core alembic downgrade -1
2. Downgrade to a specific revision: docker compose exec backend-core alembic downgrade ae1027a6acf
3. Downgrade to the base (initial state): docker compose exec backend-core alembic downgrade base

## Project Structure

```
assistcx-platform/
│
├── backend/
│   ├── agents/
│   │   ├── ...
│   ├── migrations/
│   │   ├── ...
│   ├── models/
│   │   ├── ...
│   ├── repositories/
│   │   ├── ...
│   ├── schemas/
│   │   ├── ...
│   ├── parsers/
│   │   ├── ...
│   ├── routes/
│   │   ├── ...
│   ├── tools/
│   │   ├── ...
│   ├── utils/
│   │   ├── ...
│   │
│   ├── __init__.py
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── config_ocr.py
│   ├── celery_worker.py
│   ├── database.py
│   ├── logger.py
│   ├── main.py
│   └── requirements.txt
│
├── scripts/
│   ├── build.sh
│   ├── cert.sh
│   ├── start.sh
│
├── .env
├── .gitignore
├── .gitattributes
├── build.sh
├── cert.sh
├── start.sh
├── docker-config.yml
├── docker-compose.yml
└── README.md
```

## Styling guide :

1. Always arrange functions, routes or anything in alphabetical order.
2. Imports are supposed to be in alphabetical order.
   Eg : from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
3. Standard way to styling inports :

   **#Custom libraries**  
   **#Database modules**  
   **#Default libraries**  
   **#Installed libraries**

## Creating dashboards in grafana :

1. Open {url}:4000
2. Visit dashboards page click on New > Import
3. Drag and drop the dashboard.json file available in tests > grafana.
4. Add loki connection
5. Save

## Storage Mount Configuration

### Quick Setup

1. Create the local storage directories (if not already created):
   ```bash
   mkdir -p /Users/yourname/project/storage
   ```
2. Create `mounts.json` in root directory with your local paths:

   ```json
   [
     {
       "host": "/user/host/path1",
       "container": "/mnt/data-bucket"
     },
     {
       "host": "/user/host/path2",
       "container": "/mnt/data-bucket-1"
     }
   ]
   ```

### Requirements

- At least one storage mount must be configured in `mounts.json`
- Host paths must exist on your local system
- Container paths should match the application's expected mount points
- First container path must be `/mnt/data-bucket`

### Notes

- Storage mount point config is not required in the env file (`.env`). It is automatically generated by the start script.
- `mounts.json` and `docker-compose.override.yml` are in `.gitignore` (environment-specific)
- The start script will automatically generate `docker-compose.override.yml` based on your `mounts.json`

## FAQ

1. **How to mount storage in Windows system?**  
   a. Set the following in the `.env` file:
   ```plaintext
   # Mounted storage
   STORAGE_MOUNT_POINT=./storage
   ```
   b. Bring down all containers by using:
   ```plaintext
   docker compose down
   ```
   c. Run the following commands one by one:
   ```powershell
   Remove-Item -Path ".\storage" -Recurse -Force
   New-Item -Path ".\storage" -ItemType Directory -Force
   New-Item -Path ".\storage\knowledge-data" -ItemType Directory -Force
   ```
   d. To ensure the storage is correctly created, run the following command:
   ```plaintext
   docker exec attachment_worker ls -la /mnt/data-bucket
   ```
   e. The output of the above command should start with:
   ```plaintext
   drwxrwxrwx
   ```
