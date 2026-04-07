// ─────────────────────────────────────────────────────────────────────────────
// spoke.bicep
// Outreach spoke Logic App — HTTP triggered, zero idle cost.
// Instantiated once per category in main.bicep.
//
// Triggered by hub via fire-and-forget HTTP POST.
// Logic Apps returns 202 to caller immediately; workflow runs asynchronously.
// ─────────────────────────────────────────────────────────────────────────────

param location string
param logicAppName string       // e.g. "spoke-subject-to-outreach"
param workflowDefinition object // loaded by main.bicep via loadJsonContent()

param geminiModel string = 'gemini-2.5-flash'

param tableConnectionId string
param tableConnectionApiId string
param logAnalyticsWorkspaceId string

resource spokeLogicApp 'Microsoft.Logic/workflows@2019-05-01' = {
  name: logicAppName
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
    }
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'send-to-log-analytics'
  scope: spokeLogicApp
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

#disable-next-line outputs-should-not-contain-secrets
output triggerUrl string = listCallbackUrl(
  resourceId('Microsoft.Logic/workflows/triggers', spokeLogicApp.name, 'When_an_HTTP_request_is_received'),
  '2019-05-01'
).value
