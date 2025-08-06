"""
Management command to reset authentication tokens for users
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from users.token_models import DeviceToken


class Command(BaseCommand):
    help = 'Reset authentication tokens for users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Reset token for specific user ID'
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Reset token for specific username'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Reset tokens for all users'
        )

    def handle(self, *args, **options):
        if options['user_id']:
            try:
                user = User.objects.get(id=options['user_id'])
                self.reset_user_tokens(user)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'User with ID {options["user_id"]} not found'))
                
        elif options['username']:
            try:
                user = User.objects.get(username=options['username'])
                self.reset_user_tokens(user)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'User {options["username"]} not found'))
                
        elif options['all']:
            users = User.objects.filter(is_active=True)
            self.stdout.write(f'Resetting tokens for {users.count()} active users...')
            
            for user in users:
                self.reset_user_tokens(user)
                
            self.stdout.write(self.style.SUCCESS(f'✅ Reset tokens for {users.count()} users'))
            
        else:
            self.stdout.write(self.style.ERROR('Please specify --user-id, --username, or --all'))

    def reset_user_tokens(self, user):
        # Delete old tokens
        old_token_count = Token.objects.filter(user=user).count()
        Token.objects.filter(user=user).delete()
        
        # Delete device tokens
        device_token_count = DeviceToken.objects.filter(user=user).count()
        DeviceToken.objects.filter(user=user).delete()
        
        # Create new token
        new_token = Token.objects.create(user=user)
        
        self.stdout.write(
            f'🔄 {user.get_full_name()} ({user.username}): '
            f'Deleted {old_token_count} old tokens, {device_token_count} device tokens. '
            f'New token: {new_token.key}'
        )