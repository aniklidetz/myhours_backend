# Deployment Configuration

## Overview

The CI/CD pipeline now uses configurable deployment flags through GitHub Repository Variables for better control.

## Configuration

### Repository Variables (Settings → Secrets and variables → Actions → Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `DEPLOY_STAGING` | `'1'` | Controls staging deployment (0=disabled, 1=enabled) |
| `DEPLOY_PRODUCTION` | `'1'` | Controls production deployment (0=disabled, 1=enabled) |
| `SLACK_WEBHOOK_URL` | `''` | Slack webhook URL for notifications (configure in Variables, not Secrets!) |

### Deployment Logic

**Staging Deployment:**
- Triggers on: All branches **except** `main`
- Condition: `success() && github.ref != 'refs/heads/main' && (vars.DEPLOY_STAGING || '1') == '1'`
- Purpose: Test deployments for feature branches and develop

**Production Deployment:**
- Triggers on: `main` branch only
- Condition: `success() && github.ref == 'refs/heads/main' && (vars.DEPLOY_PRODUCTION || '1') == '1'`
- Purpose: Production releases

## Benefits

1. **No Double Deployment**: Same commit won't deploy to both staging and production
2. **Configurable Gates**: Toggle deployments without editing YAML files
3. **Debug Information**: Each deployment job shows debug info for troubleshooting
4. **Concurrency Control**: Prevents deployment conflicts with `cancel-in-progress: true`
5. **Better Dependencies**: Both deployments wait for all tests to pass

## Usage Examples

### Disable All Deployments
```bash
# Set both variables to '0'
DEPLOY_STAGING=0
DEPLOY_PRODUCTION=0
```

### Enable Only Staging (for testing)
```bash
DEPLOY_STAGING=1
DEPLOY_PRODUCTION=0
```

### Normal Operation (both enabled)
```bash
DEPLOY_STAGING=1
DEPLOY_PRODUCTION=1
```

## Troubleshooting

### Deployment Skipped (0s duration)
- Check Repository Variables are set correctly
- Look for debug output in job logs
- Verify branch conditions match your workflow

### Missing Slack Notifications
- Set `SLACK_WEBHOOK_URL` in Repository Variables (not Secrets!)
- Notification only sends on successful deployments
- Check webhook URL is valid

**⚠️ Security Note**: While `SLACK_WEBHOOK_URL` is set in Variables (making it visible in logs), this is required for GitHub Actions conditionals. The URL itself is not highly sensitive as it only allows posting to a specific Slack channel. For maximum security, consider using a Slack bot token with limited permissions instead.

## Alternative Deployment Strategies

The current setup can be easily modified for other strategies:

### Deploy staging on main, production on tags
```yaml
deploy-staging:
  if: ${{ success() && github.ref == 'refs/heads/main' }}

deploy-production:
  if: ${{ success() && startsWith(github.ref, 'refs/tags/v') }}
```

### Always deploy staging, conditional production
```yaml
deploy-staging:
  if: ${{ success() }}

deploy-production:
  if: ${{ success() && github.ref == 'refs/heads/main' && env.DEPLOY_PRODUCTION == '1' }}
```