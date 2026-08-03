// Admin UI infrastructure — deliberately separate from main.bicep so the
// Logic Apps pipeline (values.yaml → sync.py → deploy.py) stays untouched.
// Deploy once: az deployment group create -g RELeadScraperGroup -f deploy/admin-ui.bicep
// Content ships separately: make deploy-be (function zip) + make deploy-azure (swa deploy).
param location string = resourceGroup().location
// Static Web Apps is not offered in eastus — nearest supported region
param swaLocation string = 'eastus2'
param apiLocation string = 'eastus2'
// This subscription currently has 0 quota for Dynamic (Y1) plans in every
// region, so the API ships as SWA *managed* functions by default. Flip this
// to true (after a quota increase) to provision the standalone Function App.
param deployFunctionApp bool = false
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

output staticWebAppHostname string = staticWebApp.properties.defaultHostname
output functionAppHostname string = deployFunctionApp ? functionApp!.properties.defaultHostName : ''
