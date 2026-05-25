// Frontend Container App (Next.js standalone).
// External ingress on port 3000; injects backend WS URL at runtime via NEXT_PUBLIC_*.
@description('Container App name.')
param name string

@description('Azure region.')
param location string

@description('Resource tags.')
param tags object = {}

@description('Resource ID of the Container Apps managed environment.')
param containerEnvId string

@description('Public URL of the backend (e.g. https://ca-backend-xxx.<region>.azurecontainerapps.io).')
param backendUrl string

@description('Container image, e.g. <acr>.azurecr.io/frontend:<tag>.')
param image string

@description('CPU cores per replica.')
param cpu string = '0.5'

@description('Memory per replica.')
param memory string = '1.0Gi'

@description('Minimum replicas.')
@minValue(0)
param minReplicas int = 1

@description('Maximum replicas.')
@minValue(1)
param maxReplicas int = 3

// Derive the wss:// URL from the https:// backend URL.
var backendWsUrl = replace(backendUrl, 'https://', 'wss://')

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    managedEnvironmentId: containerEnvId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 3000
        transport: 'auto'
        allowInsecure: false
        traffic: [
          {
            weight: 100
            latestRevision: true
          }
        ]
      }
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'NODE_ENV', value: 'production' }
            { name: 'NEXT_PUBLIC_BACKEND_URL', value: backendUrl }
            { name: 'NEXT_PUBLIC_BACKEND_WS_URL', value: backendWsUrl }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/', port: 3000 }
              initialDelaySeconds: 10
              periodSeconds: 30
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
