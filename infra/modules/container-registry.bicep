// Azure Container Registry (Basic SKU) for azd to push backend/frontend images into.
// AcrPull is granted to the workload's user-assigned managed identity so Container Apps
// can pull without admin user / API keys.
@description('ACR name (5-50 chars, alphanumeric, globally unique).')
@minLength(5)
@maxLength(50)
param name string

@description('Azure region.')
param location string

@description('Resource tags.')
param tags object = {}

@description('Principal ID of the UAMI that needs AcrPull on this registry.')
param pullPrincipalId string

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

// Built-in 'AcrPull' role.
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource pullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, pullPrincipalId, acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: pullPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output id string = registry.id
output name string = registry.name
output loginServer string = registry.properties.loginServer
