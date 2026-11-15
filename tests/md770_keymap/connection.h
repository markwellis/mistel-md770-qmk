#pragma once
typedef enum { CONNECTION_HOST_USB, CONNECTION_HOST_BLUETOOTH } connection_host_t;
connection_host_t connection_get_host(void);
