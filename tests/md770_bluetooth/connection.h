#pragma once
enum connection_host_t { CONNECTION_HOST_AUTO, CONNECTION_HOST_NONE, CONNECTION_HOST_USB, CONNECTION_HOST_BLUETOOTH };
connection_host_t connection_get_host(void);
void connection_set_host(connection_host_t);
void connection_set_host_noeeprom(connection_host_t);
