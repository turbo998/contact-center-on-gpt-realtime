// Container Apps managed environment wired to a Log Analytics workspace.
@description('Environment resource name.')
param name string

@description('Azure region.')
param location string

@description('Resource tags.')
param tags object = {}

@description('Resource ID of the Log Analytics workspace for app logs.')
param logAnalyticsWorkspaceId string

// Look up the workspace to fetch its customerId + sharedKey for the env config.
resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: last(split(logAnalyticsWorkspaceId, '/'))
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

output id string = env.id
output name string = env.name
output defaultDomain string = env.properties.defaultDomain
