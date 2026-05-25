// Top-level deployment for contact-center-on-gpt-realtime.
// See docs/06-deployment.md for the full plan.

targetScope = 'resourceGroup'

@description('Environment name supplied by azd (e.g. dev, demo).')
param environmentName string

@description('Primary region for all resources.')
param location string = resourceGroup().location

@description('Name of the existing Azure AI Foundry / Azure OpenAI account.')
param foundryAccountName string

@description('Endpoint of the Foundry account, e.g. https://<acct>.openai.azure.com')
param azureOpenAiEndpoint string

@description('Backend container image (set by azd after build/push).')
param backendImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Frontend container image (set by azd after build/push).')
param frontendImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Tags applied to every resource.')
param tags object = {
  'azd-env-name': environmentName
  project: 'contact-center-on-gpt-realtime'
}

// -- Modules -------------------------------------------------------------------

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

// Container registry — azd pushes images here; ACA pulls via UAMI (AcrPull).
module registry 'modules/container-registry.bicep' = {
  name: 'registry'
  params: {
    // ACR names must be alphanumeric only.
    name: 'acr${uniqueString(resourceGroup().id, environmentName)}'
    location: location
    tags: tags
    pullPrincipalId: managedIdentity.outputs.principalId
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
    managedIdentityClientId: managedIdentity.outputs.clientId
    image: backendImage
    azureOpenAiEndpoint: azureOpenAiEndpoint
    acrLoginServer: registry.outputs.loginServer
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
    image: frontendImage
    managedIdentityId: managedIdentity.outputs.id
    acrLoginServer: registry.outputs.loginServer
  }
}

// -- Outputs -------------------------------------------------------------------

output AZURE_RESOURCE_GROUP string = resourceGroup().name
output AZURE_LOCATION string = location
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = registry.outputs.name
output BACKEND_URL string = backend.outputs.url
output FRONTEND_URL string = frontend.outputs.url
output AZURE_MANAGED_IDENTITY_CLIENT_ID string = managedIdentity.outputs.clientId
