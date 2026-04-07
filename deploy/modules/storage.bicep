// ─────────────────────────────────────────────────────────────────────────────
// storage.bicep
// Storage Account + Tables + Azure Table API Connection.
// No queues — spokes are HTTP-triggered, zero idle cost.
// ───────────────────────────────────���─────────────────────────────────────────

param location string
param storageAccountName string
param logAnalyticsWorkspaceId string

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource tableService 'Microsoft.Storage/storageAccounts/tableServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource leadsTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-01-01' = {
  parent: tableService
  name: 'leads'
}

resource versionsTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-01-01' = {
  parent: tableService
  name: 'appversions'
}

resource configTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-01-01' = {
  parent: tableService
  name: 'config'
}

resource tableDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'send-to-log-analytics'
  scope: tableService
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      { category: 'StorageRead',   enabled: true }
      { category: 'StorageWrite',  enabled: true }
      { category: 'StorageDelete', enabled: true }
    ]
    metrics: [
      { category: 'Transaction', enabled: true }
    ]
  }
}

// ── Azure Table Storage API connection (used by hub + all spokes) ─────────────
var storageKey = storageAccount.listKeys().keys[0].value

resource tableConnection 'Microsoft.Web/connections@2016-06-01' = {
  name: 'azuretables-lead-pipeline'
  location: location
  properties: {
    displayName: 'Lead Pipeline Table Storage'
    api: {
      id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'azuretables')
    }
    parameterValues: {
      storageaccount: storageAccount.name
      sharedkey: storageKey
    }
  }
}

output storageAccountName string = storageAccount.name
output tableConnectionId string = tableConnection.id
output tableConnectionApiId string = subscriptionResourceId(
  'Microsoft.Web/locations/managedApis', location, 'azuretables'
)
