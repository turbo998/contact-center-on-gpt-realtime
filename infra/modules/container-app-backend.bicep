// Backend Container App (FastAPI / WebSocket).
// - External ingress on port 8000 (WebSocket upgrades supported by default).
// - User-assigned MI for Azure AI Foundry access via DefaultAzureCredential.
@description('Container App name.')
param name string

@description('Azure region.')
param location string

@description('Resource tags.')
param tags object = {}

@description('Resource ID of the Container Apps managed environment.')
param containerEnvId string

@description('Resource ID of the user-assigned managed identity.')
param managedIdentityId string

@description('Client ID of the UAMI (passed as AZURE_CLIENT_ID so DefaultAzureCredential picks it).')
param managedIdentityClientId string

@description('Container image, e.g. <acr>.azurecr.io/backend:<tag>.')
param image string

@description('Azure OpenAI / Foundry endpoint, e.g. https://<acct>.openai.azure.com')
param azureOpenAiEndpoint string

@description('Azure OpenAI API version.')
param azureOpenAiApiVersion string = '2024-10-01-preview'

@description('Deployment name for gpt-realtime-2 (assist).')
param deploymentRealtime2 string = 'gpt-realtime-2'

@description('Deployment name for gpt-realtime-translate.')
param deploymentTranslate string = 'gpt-realtime-translate'

@description('Deployment name for gpt-realtime-whisper.')
param deploymentWhisper string = 'gpt-realtime-whisper'

@description('CPU cores per replica.')
param cpu string = '0.5'

@description('Memory per replica.')
param memory string = '1.0Gi'

@description('Minimum replicas (keep >=1 for warm WS).')
@minValue(1)
param minReplicas int = 1

@description('Maximum replicas.')
@minValue(1)
param maxReplicas int = 3

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerEnvId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        traffic: [
          {
            weight: 100
            latestRevision: true
          }
        ]
        // CORS handled by the app itself; frontend lives on its own ACA.
      }
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'APP_ENV', value: 'production' }
            { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
            { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
            { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }
            { name: 'AZURE_OPENAI_DEPLOYMENT_REALTIME2', value: deploymentRealtime2 }
            { name: 'AZURE_OPENAI_DEPLOYMENT_TRANSLATE', value: deploymentTranslate }
            { name: 'AZURE_OPENAI_DEPLOYMENT_WHISPER', value: deploymentWhisper }
            { name: 'AUDIT_DIR', value: '/app/audit' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output id string = app.id
output name string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn
output url string = 'https://${app.properties.configuration.ingress.fqdn}'
