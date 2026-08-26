// Public UI infrastructure — deliberately separate from admin-ui.bicep and from
// main.bicep, so the Logic Apps pipeline and the admin app are both untouched.
//
//   make pub-deploy-be      (resource group comes from .env)
//
// Content ships separately: make pub-deploy-azure (SPA + managed-functions API).
param location string = resourceGroup().location
// Static Web Apps is not offered in eastus — nearest supported region, and the
// same one the admin SWA landed in
param swaLocation string = 'eastus2'

param storageAccountName string = 'releadscraper'
param staticWebAppName string = 'flynest-public'

// Service token for the alert notifier (mint with: make pub-service-token).
// Empty = the notifier Logic App is not deployed.
@secure()
param notifierServiceToken string = ''

// How often the notifier looks for new matches. 15 minutes keeps "as they
// land" honest without hammering the table.
param notifierMinutes int = 15

// Email. Azure has no free tier here — ACS Email is $0.25 per 1,000 messages,
// which at alert volumes is a couple of dollars a month. Point
// NOTIFY_EMAIL_PROVIDER at brevo instead for a hard $0.
//
// Defaults to FALSE because provisioning it needs the Microsoft.Communication
// resource provider registered on the subscription, which needs a role this
// deployment identity does not have:
//     az provider register --namespace Microsoft.Communication
// Run that as a subscription Owner, then redeploy with deployEmail=true.
param deployEmail bool = false
param communicationServiceName string = 'flynest-comms'
param emailServiceName string = 'flynest-email'

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageAccountName
}

resource tableService 'Microsoft.Storage/storageAccounts/tableServices@2023-01-01' existing = {
  parent: storageAccount
  name: 'default'
}

// ── the public app's own tables ─────────────────────────────────────────────
// Named pub* so they can never be confused with the admin app's users/sessions
// — a public token is not presentable to the admin API by construction.
var publicTables = [
  'pubusers'
  'pubsessions'
  'pubnotes'
  'pubsaved'
  'pubalerts'
  'pubalertlog'
  'pubpush'
]

resource tables 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-01-01' = [
  for name in publicTables: {
    parent: tableService
    name: name
  }
]

// ── static web app (Free) — SPA + managed functions API ─────────────────────
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

// ── email ───────────────────────────────────────────────────────────────────
// An Azure Managed Domain sends as donotreply@<guid>.azurecomm.net with no DNS
// work at all. Deliverability is fine for transactional mail; swap in a
// verified custom domain later by changing domainManagement to CustomerManaged.
resource emailService 'Microsoft.Communication/emailServices@2023-04-01' = if (deployEmail) {
  name: emailServiceName
  location: 'global'
  properties: {
    dataLocation: 'United States'
  }
}

resource managedDomain 'Microsoft.Communication/emailServices/domains@2023-04-01' = if (deployEmail) {
  parent: emailService
  name: 'AzureManagedDomain'
  location: 'global'
  properties: {
    domainManagement: 'AzureManaged'
    // open/click tracking off: these are alerts the user asked for, not marketing
    userEngagementTracking: 'Disabled'
  }
}

resource communicationService 'Microsoft.Communication/communicationServices@2023-04-01' = if (deployEmail) {
  name: communicationServiceName
  location: 'global'
  properties: {
    dataLocation: 'United States'
    linkedDomains: [
      managedDomain!.id
    ]
  }
}

// ── alert notifier — pure cron; ALL logic lives in the public API ───────────
resource notifier 'Microsoft.Logic/workflows@2019-05-01' = if (!empty(notifierServiceToken)) {
  name: 'flynest-public-alert-notifier'
  location: location
  properties: {
    state: 'Enabled'
    parameters: {
      apiToken: { value: notifierServiceToken }
    }
    definition: {
      '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
      contentVersion: '1.0.0.0'
      parameters: {
        apiToken: { type: 'securestring' }
      }
      triggers: {
        Every_Few_Minutes: {
          type: 'Recurrence'
          recurrence: {
            frequency: 'Minute'
            interval: notifierMinutes
            timeZone: 'UTC'
          }
        }
      }
      actions: {
        Run_Alerts: {
          type: 'Http'
          inputs: {
            method: 'POST'
            uri: 'https://${staticWebApp.properties.defaultHostname}/api/alerts/run'
            headers: {
              'Content-Type': 'application/json'
              'X-Public-Token': '@parameters(\'apiToken\')'
            }
            body: {
              dry_run: false
            }
            retryPolicy: { type: 'exponential', count: 2, interval: 'PT1M' }
          }
        }
      }
    }
  }
}

output staticWebAppHostname string = staticWebApp.properties.defaultHostname
output siteUrl string = 'https://${staticWebApp.properties.defaultHostname}'
output senderAddress string = deployEmail ? 'DoNotReply@${managedDomain!.properties.mailFromSenderDomain}' : ''
output communicationServiceName string = deployEmail ? communicationService!.name : ''
