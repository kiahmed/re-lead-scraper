# Azure Service Principal
source ./.env

# Create a working directory
mkdir -p ~/bicep-export && cd ~/bicep-export

# Export the entire RG as ARM JSON
az group export \
  --name ReLeadScraper-RG \
  --include-parameter-default-value \
  -o json > arm-template.json

# Decompile ARM JSON to Bicep
az bicep decompile --file arm-template.json

# Option 1: UPDATE mode (keep existing resource references)
az deployment group create \
  --resource-group ReLeadScraper-RG \
  --template-file arm-template.bicep \
  --mode Incremental
  
#Option 2: CREATE mode (clean template for new deployments)
  # make a copy to clean up
cp arm-template.bicep create-template.bicep
#Quick sed to strip common auto-generated fields:
sed -i \
  -e '/resourceGuid:/d' \
  -e '/provisioningState:/d' \
  -e '/createdTime:/d' \
  -e '/changedTime:/d' \
  -e '/uniqueId:/d' \
  create-template.bicep

#Deploy the clean version to a new RG:  
  # create new RG
az group create --name ReLeadScraper-RG-v2 --location eastus

# deploy fresh
az deployment group create \
  --resource-group ReLeadScraper-RG-v2 \
  --template-file create-template.bicep \
  --mode Complete