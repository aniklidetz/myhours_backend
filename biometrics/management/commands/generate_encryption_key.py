"""
Management command to generate encryption key for biometric data

GDPR Article 9 Compliance: Generate Fernet encryption key
"""

from django.core.management.base import BaseCommand

from biometrics.services.encryption_service import BiometricEncryptionService


class Command(BaseCommand):
    help = "Generate encryption key for biometric data (GDPR Article 9 compliance)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--test",
            action="store_true",
            help="Test the generated key with sample data",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.HTTP_INFO(
                "\n==================================================================="
            )
        )
        self.stdout.write(
            self.style.HTTP_INFO("Biometric Data Encryption Key Generator")
        )
        self.stdout.write(
            self.style.HTTP_INFO("GDPR Article 9 Compliance")
        )
        self.stdout.write(
            self.style.HTTP_INFO(
                "==================================================================="
            )
        )

        # Generate key
        self.stdout.write("\n📝 Generating encryption key...")
        key = BiometricEncryptionService.generate_key()

        self.stdout.write(self.style.SUCCESS("\n✅ Encryption key generated successfully!"))
        self.stdout.write(f"\n{self.style.WARNING('IMPORTANT: Store this key securely!')}")
        self.stdout.write(
            self.style.WARNING(
                "This key is required to encrypt/decrypt biometric embeddings."
            )
        )

        self.stdout.write(f"\n{self.style.HTTP_INFO('Encryption Key:')}")
        self.stdout.write(self.style.SUCCESS(f"{key}"))

        self.stdout.write(f"\n{self.style.HTTP_INFO('Usage Instructions:')}")
        self.stdout.write("1. Add to your .env file:")
        self.stdout.write(f"   BIOMETRIC_ENCRYPTION_KEY={key}")
        self.stdout.write("\n2. For production, use secure secret management:")
        self.stdout.write("   - AWS Secrets Manager")
        self.stdout.write("   - HashiCorp Vault")
        self.stdout.write("   - Azure Key Vault")
        self.stdout.write("   - Google Cloud Secret Manager")

        # Test the key if requested
        if options["test"]:
            self.stdout.write(f"\n{self.style.HTTP_INFO('Testing encryption key...')}")
            try:
                # Create service instance with the new key
                import os

                os.environ["BIOMETRIC_ENCRYPTION_KEY"] = key

                # Test encryption/decryption
                from django.conf import settings

                settings.BIOMETRIC_ENCRYPTION_KEY = key
                service = BiometricEncryptionService()

                test_data = [
                    {"vector": [0.1, 0.2, 0.3], "quality": 0.95, "index": 0},
                    {"vector": [0.4, 0.5, 0.6], "quality": 0.88, "index": 1},
                ]

                encrypted = service.encrypt_embeddings(test_data)
                decrypted = service.decrypt_embeddings(encrypted)

                if decrypted == test_data:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "✅ Encryption test passed - key is valid!"
                        )
                    )
                    self.stdout.write(
                        f"   - Encrypted size: {len(encrypted)} bytes"
                    )
                    self.stdout.write(
                        f"   - Original data: {len(str(test_data))} bytes"
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            "❌ Encryption test failed - data integrity issue"
                        )
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Encryption test failed: {str(e)}")
                )

        self.stdout.write(
            self.style.HTTP_INFO(
                "\n==================================================================="
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "⚠️  SECURITY WARNING: Never commit this key to version control!"
            )
        )
        self.stdout.write(
            self.style.WARNING("⚠️  Store securely and rotate periodically!")
        )
        self.stdout.write(
            self.style.HTTP_INFO(
                "===================================================================\n"
            )
        )
