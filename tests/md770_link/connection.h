#pragma once
enum connection_host_t { CONNECTION_HOST_NONE, CONNECTION_HOST_USB };
void connection_set_host_noeeprom(connection_host_t host);

struct { unsigned state; } inline USBD1;
