source ./.env
SP_ID=$AZURE_SUBSCRIPTION_ID
SCOPE="/subscriptions/$AZURE_SUBSCRIPTION_ID/resourceGroups/$AZURE_RESOURCE_GROUP"

# Read all resource configs (you likely have this already via Contributor)
az role assignment create --assignee $SP_ID --role "Reader" --scope $SCOPE

# Read logs, metrics, diagnostic settings
az role assignment create --assignee $SP_ID --role "Monitoring Reader" --scope $SCOPE

# Read Log Analytics workspace data (the actual log queries)
az role assignment create --assignee $SP_ID --role "Log Analytics Reader" --scope $SCOPE

#verify
az role assignment list \
  --assignee $SP_ID \
  --resource-group RELeadScraperGroup \
  --query "[].{role:roleDefinitionName, scope:scope}" \
  -o table

#test it 
# list logic apps
az logic workflow list --resource-group RELeadScraperGroup -o table

# see run history
az logic workflow-run list \
  --resource-group RELeadScraperGroup \
  --workflow-name <logic-app-name> \
  -o table

# see a specific run's actions
az logic workflow-run-action list \
  --resource-group RELeadScraperGroup \
  --workflow-name <logic-app-name> \
  --run-name <run-id> \
  -o table
#Qery la directy
WS_NAME=$(az monitor log-analytics workspace list \
  --resource-group RELeadScraperGroup \
  --query "[0].name" -o tsv)

# run a KQL query against the logs
az monitor log-analytics query \
  --workspace $WS_NAME \
  --analytics-query "AzureDiagnostics | where ResourceProvider == 'MICROSOFT.LOGIC' | take 10" \
  -o table

  # see all roles that grant a specific action
az role definition list \
  --query "[?permissions[?actions[?contains(@, 'Microsoft.Logic')]]].[roleName]" \
  -o tsv