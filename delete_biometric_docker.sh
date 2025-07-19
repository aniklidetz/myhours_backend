#!/bin/bash

# Script to delete biometric data for a specific employee in Docker

if [ "$#" -ne 1 ]; then
    echo "Usage: ./delete_biometric_docker.sh <employee_id>"
    echo "Example: ./delete_biometric_docker.sh 29"
    exit 1
fi

EMPLOYEE_ID=$1

echo "🗑️  Deleting biometric data for employee ID: $EMPLOYEE_ID"

# Delete from MongoDB
docker exec myhours_web python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
import django
django.setup()

from biometrics.services.mongodb_service import mongodb_service
from biometrics.models import BiometricProfile

employee_id = $EMPLOYEE_ID

# Delete from MongoDB
deleted = mongodb_service.delete_embeddings(employee_id)
print(f'MongoDB: {\"✅ Deleted\" if deleted else \"❌ Not found\"}')

# Delete from PostgreSQL
try:
    profile = BiometricProfile.objects.get(employee_id=employee_id)
    profile.delete()
    print('PostgreSQL: ✅ Deleted')
except BiometricProfile.DoesNotExist:
    print('PostgreSQL: ❌ Not found')
except Exception as e:
    print(f'PostgreSQL: ❌ Error - {e}')

print(f'\\n✅ Employee {employee_id} biometric data cleared')
"