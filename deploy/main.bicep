// ─────────────────────────────────────────────────────────────────────────────
// main.bicep — deploys the full lead pipeline
//
// Resources:  1 Storage Account  +  2 Tables  +  1 API Connection
//             1 Hub Logic App  +  7 Spoke Logic Apps
//
// No queues — spokes use HTTP triggers (zero idle/polling cost).
// Hub resolves each spoke's trigger URL at deploy time and stores them
// as a secure parameter so it can fire-and-forget HTTP calls at runtime.
//
// Deploy flow:
//   python3 sync.py --apply    # regenerate deploy/workflows/*.json from values.yaml
//   python3 deploy.py          # runs this template
// ─────────────────────────────────────────────────────────────────────────────

param location string = 'eastus'
param storageAccountName string = 'releadscraper'
param logAnalyticsWorkspaceName string = 'RELeadScraperLogAnalytics'

param geminiModel string = 'gemini-2.5-flash'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ── Storage ───────────────────────────────────────────────────────────────────
module storage './modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    storageAccountName: storageAccountName
    logAnalyticsWorkspaceId: logAnalytics.id
  }
}

// ── Spokes (deployed before hub so their trigger URLs can be resolved) ────────
module spokeSubjectTo './modules/spoke.bicep' = {
  name: 'spoke-subject-to'
  params: {
    location: location
    logicAppName: 'spoke-subject-to-outreach'
    workflowDefinition: loadJsonContent('./workflows/spoke-subject-to-workflow.json')
    geminiModel: geminiModel
    tableConnectionId: storage.outputs.tableConnectionId
    tableConnectionApiId: storage.outputs.tableConnectionApiId
    logAnalyticsWorkspaceId: logAnalytics.id
  }
}

module spokeSellerFinance './modules/spoke.bicep' = {
  name: 'spoke-seller-finance'
  params: {
    location: location
    logicAppName: 'spoke-seller-finance-outreach'
    workflowDefinition: loadJsonContent('./workflows/spoke-seller-finance-workflow.json')
    geminiModel: geminiModel
    tableConnectionId: storage.outputs.tableConnectionId
    tableConnectionApiId: storage.outputs.tableConnectionApiId
    logAnalyticsWorkspaceId: logAnalytics.id
  }
}

module spokeHybrid './modules/spoke.bicep' = {
  name: 'spoke-hybrid'
  params: {
    location: location
    logicAppName: 'spoke-hybrid-outreach'
    workflowDefinition: loadJsonContent('./workflows/spoke-hybrid-workflow.json')
    geminiModel: geminiModel
    tableConnectionId: storage.outputs.tableConnectionId
    tableConnectionApiId: storage.outputs.tableConnectionApiId
    logAnalyticsWorkspaceId: logAnalytics.id
  }
}

module spokeFixFlip './modules/spoke.bicep' = {
  name: 'spoke-fix-flip'
  params: {
    location: location
    logicAppName: 'spoke-fix-flip-outreach'
    workflowDefinition: loadJsonContent('./workflows/spoke-fix-flip-workflow.json')
    geminiModel: geminiModel
    tableConnectionId: storage.outputs.tableConnectionId
    tableConnectionApiId: storage.outputs.tableConnectionApiId
    logAnalyticsWorkspaceId: logAnalytics.id
  }
}

module spokeJVWholesale './modules/spoke.bicep' = {
  name: 'spoke-jv-wholesale'
  params: {
    location: location
    logicAppName: 'spoke-jv-wholesale-outreach'
    workflowDefinition: loadJsonContent('./workflows/spoke-jv-wholesale-workflow.json')
    geminiModel: geminiModel
    tableConnectionId: storage.outputs.tableConnectionId
    tableConnectionApiId: storage.outputs.tableConnectionApiId
    logAnalyticsWorkspaceId: logAnalytics.id
  }
}

module spokeBuyersLooking './modules/spoke.bicep' = {
  name: 'spoke-buyers-looking'
  params: {
    location: location
    logicAppName: 'spoke-buyers-looking-outreach'
    workflowDefinition: loadJsonContent('./workflows/spoke-buyers-looking-workflow.json')
    geminiModel: geminiModel
    tableConnectionId: storage.outputs.tableConnectionId
    tableConnectionApiId: storage.outputs.tableConnectionApiId
    logAnalyticsWorkspaceId: logAnalytics.id
  }
}

module spokeRegular './modules/spoke.bicep' = {
  name: 'spoke-regular'
  params: {
    location: location
    logicAppName: 'spoke-regular-outreach'
    workflowDefinition: loadJsonContent('./workflows/spoke-regular-workflow.json')
    geminiModel: geminiModel
    tableConnectionId: storage.outputs.tableConnectionId
    tableConnectionApiId: storage.outputs.tableConnectionApiId
    logAnalyticsWorkspaceId: logAnalytics.id
  }
}

// ── Hub (deployed after spokes — needs their trigger URLs) ──────────────────��
module hub './modules/hub.bicep' = {
  name: 'hub'
  params: {
    location: location
    geminiModel: geminiModel
    tableConnectionId: storage.outputs.tableConnectionId
    tableConnectionApiId: storage.outputs.tableConnectionApiId
    spokeUrls: {
      'Subject-To':      spokeSubjectTo.outputs.triggerUrl
      'Seller Finance':  spokeSellerFinance.outputs.triggerUrl
      'Hybrid':          spokeHybrid.outputs.triggerUrl
      'Fix & Flip':      spokeFixFlip.outputs.triggerUrl
      'JV or Wholesale': spokeJVWholesale.outputs.triggerUrl
      'Buyers Looking':  spokeBuyersLooking.outputs.triggerUrl
      'Regular':         spokeRegular.outputs.triggerUrl
    }
    logAnalyticsWorkspaceId: logAnalytics.id
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────
#disable-next-line outputs-should-not-contain-secrets
output hubTriggerUrl string = hub.outputs.triggerUrl
output storageAccountName string = storage.outputs.storageAccountName
