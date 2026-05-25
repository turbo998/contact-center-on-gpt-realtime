// Top-level deployment for contact-center-on-gpt-realtime.
// See docs/06-deployment.md for the full plan.
// TODO (issue #19 bicep-infra): wire actual modules.

targetScope = 'resourceGroup'

@description('Environment name supplied by azd (e.g. dev, demo).')
param environmentName string

@description('Primary region for all resources.')
param location string = resourceGroup().location

@description('Existing or to-be-created Azure OpenAI / Foundry account name.')
param foundryAccountName string

@description('Tags applied to every resource.')
param tags object = {
  'azd-env-name': environmentName
  project: 'contact-center-on-gpt-realtime'
}

// -- Modules (placeholders) ----------------------------------------------------

module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'logAnalytics'
  params: {
    name: 'log-${environmentName}'
    location: location
    tags: tags
  }
}

module containerEnv 'modules/container-env.bicep' = {
  name: 'containerEnv'
  params: {
    name: 'cae-${environmentName}'
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
  }
}

module managedIdentity 'modules/managed-identity.bicep' = {
  name: 'mi'
  params: {
    name: 'mi-${environmentName}'
    location: location
    tags: tags
  }
}

module foundryRole 'modules/foundry-role.bicep' = {
  name: 'foundryRole'
  params: {
    foundryAccountName: foundryAccountName
    principalId: managedIdentity.outputs.principalId
  }
}

module backend 'modules/container-app-backend.bicep' = {
  name: 'backend'
  params: {
    name: 'ca-backend-${environmentName}'
    location: location
    tags: tags
    containerEnvId: containerEnv.outputs.id
    managedIdentityId: managedIdentity.outputs.id
  }
}

module frontend 'modules/container-app-frontend.bicep' = {
  name: 'frontend'
  params: {
    name: 'ca-frontend-${environmentName}'
    location: location
    tags: tags
    containerEnvId: containerEnv.outputs.id
    backendUrl: backend.outputs.url
  }
}

// -- Outputs -------------------------------------------------------------------

output BACKEND_URL string = backend.outputs.url
output FRONTEND_URL string = frontend.outputs.url
