// Admin UI infrastructure — deliberately separate from main.bicep so the
// Logic Apps pipeline (values.yaml → sync.py → deploy.py) stays untouched.
// Deploy once: make deploy-be   (resource group comes from .env)
// Content ships separately: make deploy-be (function zip) + make deploy-azure (swa deploy).
param location string = resourceGroup().location
// Static Web Apps is not offered in eastus — nearest supported region
param swaLocation string = 'eastus2'
param apiLocation string = 'eastus2'
// This subscription currently has 0 quota for Dynamic (Y1) plans in every
// region, so the API ships as SWA *managed* functions by default. Flip this
// to true (after a quota increase) to provision the standalone Function App.
param deployFunctionApp bool = false
// Service token for the monthly purge sweep (mint with: make service-token).
// Empty = the sweep Logic App is not deployed.
@secure()
param purgeServiceToken string = ''

param storageAccountName string = 'releadscraper'
param staticWebAppName string = 'flynest-admin'
param functionAppName string = 'flynest-admin-api'

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageAccountName
}

// ── admin tables in the existing account ─────────────────────────────────────
resource tableService 'Microsoft.Storage/storageAccounts/tableServices@2023-01-01' existing = {
  parent: storageAccount
  name: 'default'
}

resource usersTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-01-01' = {
  parent: tableService
  name: 'users'
}

resource sessionsTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-01-01' = {
  parent: tableService
  name: 'sessions'
}

resource interactionsTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-01-01' = {
  parent: tableService
  name: 'interactions'
}

// ── static web app (Free) — SPA only; API is the standalone function app ────
resource staticWebApp 'Microsoft.Web/staticSites@2023-01-01' = {
  name: staticWebAppName
  location: swaLocation
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    stagingEnvironmentPolicy: 'Enabled'
    allowConfigFileUpdates: true
  }
}

// ── function app (Linux consumption) ────────────────────────────────────────
var connectionString = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'

resource plan 'Microsoft.Web/serverfarms@2023-01-01' = if (deployFunctionApp) {
  name: '${functionAppName}-plan'
  location: apiLocation
  kind: 'functionapp'
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  properties: {
    reserved: true // linux
  }
}

resource functionApp 'Microsoft.Web/sites@2023-01-01' = if (deployFunctionApp) {
  name: functionAppName
  location: apiLocation
  kind: 'functionapp,linux'
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.11'
      cors: {
        allowedOrigins: [
          'https://${staticWebApp.properties.defaultHostname}'
          'http://localhost:5173'
        ]
      }
      appSettings: [
        { name: 'AzureWebJobsStorage', value: connectionString }
        { name: 'AZURE_STORAGE_CONNECTION_STRING', value: connectionString }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'ENABLE_ORYX_BUILD', value: 'true' }
      ]
    }
  }
}

// ── monthly purge sweep — pure cron; ALL purge logic lives in the admin API ──
// TTLs (days) per category; adjust here and re-deploy to tune retention.
var purgeTtlDays = {
  Others: 15
  Regular: 30
  'Fix & Flip': 30
  'JV or Wholesale': 30
  'Buyers Looking': 30
  'Subject-To': 30
  'Seller Finance': 60
  Hybrid: 60
}

resource purgeSweep 'Microsoft.Logic/workflows@2019-05-01' = if (!empty(purgeServiceToken)) {
  name: 'flynest-admin-purge-sweep'
  location: location
  properties: {
    state: 'Enabled'
    parameters: {
      apiToken: { value: purgeServiceToken }
    }
    definition: {
      '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
      contentVersion: '1.0.0.0'
      parameters: {
        apiToken: { type: 'securestring' }
      }
      triggers: {
        Monthly: {
          type: 'Recurrence'
          recurrence: {
            frequency: 'Month'
            interval: 1
            schedule: { hours: [3], minutes: [0], monthDays: [1] }
            timeZone: 'UTC'
          }
        }
      }
      actions: {
        Purge_Old_Leads: {
          type: 'Http'
          inputs: {
            method: 'POST'
            uri: 'https://${staticWebApp.properties.defaultHostname}/api/leads/purge'
            headers: {
              'Content-Type': 'application/json'
              'X-Admin-Token': '@parameters(\'apiToken\')'
            }
            body: {
              ttl_days: purgeTtlDays
              dry_run: false
              include_worked: false
            }
            retryPolicy: { type: 'exponential', count: 3, interval: 'PT1M' }
          }
        }
      }
    }
  }
}

output staticWebAppHostname string = staticWebApp.properties.defaultHostname
output functionAppHostname string = deployFunctionApp ? functionApp!.properties.defaultHostName : ''
