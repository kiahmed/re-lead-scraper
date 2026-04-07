// ─────────────────────────────────────────────────────────────────────────────
// hub.bicep
// filterProcessCreativeLeads — the hub Logic App.
// Receives webhook, filters, classifies, then fires HTTP to each spoke.
// spokeUrls is a map of category → spoke trigger URL, resolved at deploy time.
// ─────────────────────────────────────────────────────────────────────────────

param location string

param geminiModel string = 'gemini-2.5-flash'

param tableConnectionId string
param tableConnectionApiId string
param logAnalyticsWorkspaceId string

// Map of category name → spoke trigger URL (e.g. {"Subject-To": "https://..."})
// Populated from spoke module outputs in main.bicep
param spokeUrls object

var workflowDefinition = loadJsonContent('../workflows/hub-workflow.json')

resource hubLogicApp 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'filterProcessCreativeLeads'
  location: location
  properties: {
    state: 'Enabled'
    definition: workflowDefinition
    parameters: {
      '$connections': {
        value: {
          azuretables: {
            connectionId: tableConnectionId
            connectionName: 'azuretables-lead-pipeline'
            id: tableConnectionApiId
          }
        }
      }
      geminiModel:  { value: geminiModel }
      spokeUrls:    { value: spokeUrls }
    }
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'filterProcessCreativeLeads_RunLog'
  scope: hubLogicApp
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      { category: 'WorkflowRuntime', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

output logicAppName string = hubLogicApp.name
#disable-next-line outputs-should-not-contain-secrets
output triggerUrl string = listCallbackUrl(
  resourceId('Microsoft.Logic/workflows/triggers', hubLogicApp.name, 'When_an_HTTP_request_is_received'),
  '2019-05-01'
).value
