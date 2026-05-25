// Container App: backend (FastAPI)
// TODO (issue #19 bicep-infra): implement.
param name string
param location string
param tags object = {}
param containerEnvId string
param managedIdentityId string
output url string = ''
