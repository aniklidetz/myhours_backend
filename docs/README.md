# MyHours Backend Documentation

This directory contains comprehensive documentation for the MyHours backend system.

## 📁 Documentation Structure

### 🏗️ Architecture & Core
- **[CLEAN_ARCHITECTURE_REPORT.md](./CLEAN_ARCHITECTURE_REPORT.md)** - System architecture overview and design principles

### 📱 Features
- **[COMPENSATORY_DAYS_SOLUTION_SUMMARY.md](./features/COMPENSATORY_DAYS_SOLUTION_SUMMARY.md)** - Israeli labor law compliance implementation
- **[INVITATION_FLOW.md](./features/INVITATION_FLOW.md)** - Employee invitation system
- **[simple_notification_guide.md](./features/simple_notification_guide.md)** - Push notification system
- **[LOG_OPTIMIZATION_GUIDE.md](./features/LOG_OPTIMIZATION_GUIDE.md)** - Log rotation and optimization system

### 📊 Status & Reports  
- **[FINAL_STATUS.md](./status/FINAL_STATUS.md)** - Current system status and capabilities
- **[WEEKLY_HOUR_FIX_REPORT.md](./status/WEEKLY_HOUR_FIX_REPORT.md)** - Weekly hours calculation improvements
- **[deployment_warnings.md](./status/deployment_warnings.md)** - Production deployment considerations

### 🚀 Deployment
- **[PRODUCTION_DEPLOY.md](./deployment/PRODUCTION_DEPLOY.md)** - Production deployment guide
- **[TESTING.md](./TESTING.md)** - Testing procedures and guidelines

### 📚 Archive
- **[archive/](./archive/)** - Detailed technical documentation and historical reports

## 🎯 Quick Start

### For Developers
1. Read [CLEAN_ARCHITECTURE_REPORT.md](./CLEAN_ARCHITECTURE_REPORT.md) for system overview
2. Check [TESTING.md](./TESTING.md) for testing procedures
3. Review relevant feature documentation in [features/](./features/)

### For DevOps/Deployment
1. Check [status/FINAL_STATUS.md](./status/FINAL_STATUS.md) for current system state
2. Review [deployment/PRODUCTION_DEPLOY.md](./deployment/PRODUCTION_DEPLOY.md) for deployment steps
3. Check [status/deployment_warnings.md](./status/deployment_warnings.md) for production considerations

### For Project Managers
1. Review [status/FINAL_STATUS.md](./status/FINAL_STATUS.md) for project completion status
2. Check feature documentation in [features/](./features/) for implemented capabilities

## 📋 System Overview

### Core Features Implemented
- ✅ **Biometric System** - Face recognition check-in/check-out
- ✅ **Payroll Calculations** - Israeli labor law compliant salary processing  
- ✅ **Compensatory Days** - Holiday and Sabbath work compensation
- ✅ **Employee Management** - User roles, permissions, invitations
- ✅ **Work Time Tracking** - Check-in/check-out with location and break tracking
- ✅ **Notification System** - Smart work hour notifications

### Technologies
- **Backend**: Django 5.1.6 + Django REST Framework
- **Databases**: PostgreSQL (primary), MongoDB (biometrics), Redis (cache)
- **Authentication**: Token-based with device management
- **Testing**: pytest with comprehensive test coverage
- **Deployment**: Docker containerization ready

## 🔧 Maintenance

This documentation is organized to minimize duplication and maintain clarity:
- **Active documentation** is in the main docs directory
- **Detailed technical specs** are archived in `archive/`
- **Feature-specific docs** are in `features/`
- **Status reports** are in `status/`

Last updated: August 2025