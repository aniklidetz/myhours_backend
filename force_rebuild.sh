#!/bin/bash
echo "Forcing Docker rebuild..."
docker-compose down
docker-compose build --no-cache web
docker-compose up -d web