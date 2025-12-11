# Layer7 Load Balancer

## Quick Start

1. **Prepare Configuration**:  
   Edit `config.yml` to define your `listeners` and `target_groups`.

|Field|Description|Type|Required|Default|
|-|-|-|-|-|
|`listeners`|List of listener rules that define how requests are routed to target groups|List|Yes|N/A|
|`listeners[].path_prefix`|Path prefix to match incoming requests|String|Yes|N/A|
|`listeners[].path_rewrite`|Path to rewrite before forwarding to the target group|String|No|`""` (no rewrite)|
|`listeners[].target_group`|Name of the target group to route requests to|String|Yes|N/A|
|`target_groups`|List of target groups that define upstream servers|List|Yes|N/A|
|`target_groups[].name`|Name of the target group|String|Yes|N/A|
|`target_groups[].targets`|List of upstream servers in the target group|List|Yes|N/A|
|`target_groups[].targets[].hostname`|Hostname or IP address of the upstream server|String|Yes|N/A|
|`target_groups[].targets[].port`|Port of the upstream server|Int|Yes|N/A|
|`target_groups[].targets[].weight`|Weight for weighted load balancing|Int|No|1|
|`target_groups[].targets[].healthcheck.path`|Path for the health check endpoint|String|No|`"/"`|
|`target_groups[].targets[].healthcheck.status_code`|List of acceptable HTTP status codes for health checks|List|No|`[200]`|
|`target_groups[].targets[].healthcheck.timeout`|Timeout for health check requests (in seconds)|Int|No|2|

2. **Set Environment Variables**:  
   Create a `.env` file or export the following variables:  

|Variable|Description|Type|Options|Default|
|-|-|-|-|-|
|`CONFIG_FILE`|Location of the file used to define Listeners and Target Groups|String|File Path|`config.yml`|
|`LOG_LEVEL`|Load balancer LOG LEVEL. Bear in mind, all logging is done only in DEBUG.|String|`DEBUG` `INFO`|`INFO`|
|`LISTENER_PORT`|Port where the load balancer CONTAINER will listen. Make sure to match with the correct docker port|Int|Any Port Available|80|
|`CONNECTION_TIMEOUT`|Connection timeout for when the LB is trying to reach the selected upstream server (In Seconds)|Int|Any Integer number|2|
|`LOAD_BALANCING_ALGORITHM`|Algorithm used by LB for ALL target groups|String|`ROUND_ROBIN` `WEIGHTED`|`ROUND_ROBIN`|


3. **Build the Docker Image**:  
   - For x86_64:  
     ```bash
     ./x86_64-build.sh
     ```  
   - For ARM64:  
     ```bash
     ./arm64-build.sh
     ```

4. **Run with Docker Compose**:  
   ```bash
   docker-compose up --build

5. Available features:

- **Path-Based Routing**:
  - Route requests based on `path_prefix` defined in `listeners`.
  - Optionally rewrite paths before forwarding to target groups.

- **Load Balancing Algorithms**:
  - `ROUND_ROBIN`: Distributes requests evenly across all healthy targets.
  - `WEIGHTED`: Distributes requests based on target weights.

- **Health Checks**:
  - Periodically checks the health of upstream servers.
  - Supports custom health check paths, status codes, and timeouts.

- **Dynamic DNS Resolution**:
  - Resolves hostnames to multiple IP addresses and adds them as targets.

- **Environment Variable Configuration**:
  - Configure key parameters such as `LISTENER_PORT`, `CONNECTION_TIMEOUT`, and `LOAD_BALANCING_ALGORITHM`.

- **Logging**:
  - Detailed logs for request handling, health checks, and server selection.
  - Supports rotating log files to manage log size.

- **Docker Support**:
  - Predefined `Dockerfile` and `docker-compose.yml` for easy deployment.
  - Multi-architecture builds for `x86_64` and `arm64`.
