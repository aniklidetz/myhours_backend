#!/bin/bash

# Simple one-liner biometric cleanup
# Usage: ./cleanup_biometric_simple.sh 11
# Or: ./cleanup_biometric_simple.sh 11 force

EMPLOYEE_ID=$1
FORCE=$2

if [ -z "$EMPLOYEE_ID" ]; then
    echo "Usage: $0 <employee_id> [force]"
    echo "Example: $0 11"
    echo "Example: $0 11 force"
    exit 1
fi

echo "🧹 Cleaning biometric data for employee $EMPLOYEE_ID..."

if [ "$FORCE" = "force" ]; then
    echo "🔨 Using FORCE mode - will clean both databases directly"
    docker-compose exec web python manage.py shell -c "
from biometrics.services.enhanced_biometric_service import enhanced_biometric_service
from biometrics.models import BiometricProfile  
from biometrics.services.mongodb_repository import MongoBiometricRepository
from django.utils import timezone

print('Employee $EMPLOYEE_ID - Force cleanup starting...')

# Method 1: Try enhanced service first
try:
    success = enhanced_biometric_service.delete_biometric($EMPLOYEE_ID)
    print(f'Enhanced service result: {success}')
except Exception as e:
    print(f'Enhanced service error: {e}')

# Method 2: Direct database cleanup
try:
    # Clean PostgreSQL
    updated = BiometricProfile.objects.filter(employee_id=$EMPLOYEE_ID).update(
        is_active=False, 
        embeddings_count=0,
        last_updated=timezone.now()
    )
    print(f'PostgreSQL profiles updated: {updated}')
    
    # Clean MongoDB  
    mongo_repo = MongoBiometricRepository()
    mongo_deleted = mongo_repo.delete_embeddings($EMPLOYEE_ID)
    print(f'MongoDB deletion result: {mongo_deleted}')
    
    # Verify final state
    final_status = enhanced_biometric_service.get_employee_biometric_status($EMPLOYEE_ID)
    pg_exists = final_status.get('postgresql', {}).get('exists', False) 
    mongo_exists = final_status.get('mongodb', {}).get('exists', False)
    
    print(f'Final verification:')
    print(f'  PostgreSQL active: {pg_exists}')
    print(f'  MongoDB exists: {mongo_exists}')
    
    if not pg_exists and not mongo_exists:
        print('SUCCESS: All biometric data cleaned')
    else:
        print('WARNING: Some data may still exist')
        
except Exception as e:
    print(f'Direct cleanup error: {e}')
"
else
    echo " Using standard cleanup method"
    docker-compose exec web python manage.py shell -c "
from biometrics.services.enhanced_biometric_service import enhanced_biometric_service

print('Employee $EMPLOYEE_ID - Standard cleanup starting...')
success = enhanced_biometric_service.delete_biometric($EMPLOYEE_ID)
print(f'Cleanup result: {success}')

if success:
    status = enhanced_biometric_service.get_employee_biometric_status($EMPLOYEE_ID)
    pg_exists = status.get('postgresql', {}).get('exists', False)
    mongo_exists = status.get('mongodb', {}).get('exists', False)
    
    if pg_exists or mongo_exists:
        print('⚠️  Some data still exists. Try running with \"force\" parameter')
        print(f'  PostgreSQL: {pg_exists}, MongoDB: {mongo_exists}')
    else:
        print('SUCCESS: All data cleaned')
else:
    print('Cleanup failed. Try running with \"force\" parameter')
"
fi

echo "Cleanup script finished"