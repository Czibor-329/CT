下面把前面讨论的**可增加的观测特征**整理成一个结构化表格，方便你设计 obs。
按 **资源级 → 段级 → 接口 → 全局结构** 四层组织，这样既能表达局部状态，又能让策略看到**上下游瓶颈与节拍关系**。

------

# 1 资源级特征（PM / TM / Buffer）

描述每个具体资源当前状态，是最基础的信息。

| 类别   | 特征名                            | 含义                      | 类型  | 归一化建议              | 作用           |
| ------ | --------------------------------- | ------------------------- | ----- | ----------------------- | -------------- |
| PM     | occupied                          | 腔室是否有晶圆            | bool  | 0/1                     | 判断资源占用   |
| PM     | processing                        | 是否正在加工              | bool  | 0/1                     | 区分加工/等待  |
| PM     | done_waiting_pick                 | 是否加工完成等待取片      | bool  | 0/1                     | 防止驻留超时   |
| PM     | remaining_process_ratio           | 剩余加工时间比例          | float | `remaining / proc_time` | 判断何时释放   |
| PM     | wafer_stay_time_ratio             | 晶圆停留时间比例          | float | `stay / hold_limit`     | 监控驻留       |
| PM     | remaining_hold_slack_ratio        | 剩余安全驻留时间          | float | `slack / hold_limit`    | 判断紧急程度   |
| PM     | is_cleaning                       | 是否正在清洗              | bool  | 0/1                     | 清洗期间不可用 |
| PM     | clean_remaining_ratio             | 清洗剩余时间              | float | `/150`                  | 判断何时恢复   |
| PM     | remaining_runs_before_clean_ratio | 距离下次清洗剩余加工次数  | float | `/3`                    | 提前规避清洗   |
| TM     | occupied                          | 机械手是否忙              | bool  | 0/1                     | 判断是否可搬运 |
| TM     | carrying_wafer                    | 是否携带晶圆              | bool  | 0/1                     | 控制调度       |
| TM     | remaining_transfer_ratio          | 剩余搬运时间比例          | float | `/transfer_time`        | 预测释放       |
| Buffer | occupancy_ratio                   | Buffer 当前占用比例       | float | `/capacity`             | 判断拥堵       |
| Buffer | oldest_wait_ratio                 | Buffer 最老晶圆等待时间   | float | `/hold_limit`           | 防止过久停留   |
| Buffer | min_slack_ratio                   | Buffer 中最小剩余驻留时间 | float | `/hold_limit`           | 提醒风险       |
| Buffer | urgent_wafers_ratio               | Buffer 中紧急晶圆比例     | float | `/buffer_size`          | 监控风险       |

------

# 2 段级 Summary（Front / Rear Stage）

描述**整段设备负载情况**，帮助策略理解节拍。

| 类别        | 特征名                   | 含义                 | 类型  | 归一化建议       | 作用           |
| ----------- | ------------------------ | -------------------- | ----- | ---------------- | -------------- |
| Front stage | front_wip                | 前段在制品数量       | int   | `/max_wip`       | 判断拥堵       |
| Front stage | front_busy_ratio         | 前段机器忙碌比例     | float | `/machine_count` | 判断负载       |
| Front stage | front_avg_remaining_time | 前段平均剩余加工时间 | float | `/mean_proc`     | 预测释放       |
| Front stage | front_release_pressure   | 前段释放压力         | float | `/machine_count` | 判断 push 强度 |
| Rear stage  | rear_wip                 | 后段在制品数量       | int   | `/max_wip`       | 判断拥堵       |
| Rear stage  | rear_busy_ratio          | 后段机器忙碌比例     | float | `/machine_count` | 判断瓶颈       |
| Rear stage  | rear_avg_remaining_time  | 后段平均剩余加工时间 | float | `/mean_proc`     | 预测吞吐       |
| Rear stage  | rear_available_capacity  | 后段可用能力         | float | `/machine_count` | 判断是否能接片 |

------

# 3 接口层（LLC / LLD Buffer）

级联设备最关键的瓶颈信息。

| 类别      | 特征名                   | 含义                | 类型  | 归一化建议  | 作用         |
| --------- | ------------------------ | ------------------- | ----- | ----------- | ------------ |
| LLC       | llc_occ                  | LLC buffer 占用比例 | float | `/capacity` | 判断入口拥堵 |
| LLD       | lld_occ                  | LLD buffer 占用比例 | float | `/capacity` | 判断出口拥堵 |
| Interface | llc_congestion_ratio     | LLC 拥堵程度        | float | `/capacity` | 控制前段释放 |
| Interface | downstream_blocking_risk | 下游阻塞风险        | float | 统计量      | 提醒 delay   |

------

# 4 结构性静态特征（Instance-level）

用于**泛化不同设备结构与工艺时间**。

| 类别      | 特征名               | 含义             | 类型  | 归一化建议                    | 作用         |
| --------- | -------------------- | ---------------- | ----- | ----------------------------- | ------------ |
| Structure | front_parallelism    | 前段并行机器数   | int   | `/max_machine`                | 表示能力     |
| Structure | rear_parallelism     | 后段并行机器数   | int   | `/max_machine`                | 表示能力     |
| Structure | front_mean_proc_time | 前段平均加工时间 | float | `/mean_proc`                  | 表示节拍     |
| Structure | rear_mean_proc_time  | 后段平均加工时间 | float | `/mean_proc`                  | 表示节拍     |
| Structure | buffer_capacity      | Buffer 容量      | int   | `/max_buffer`                 | 表示缓冲能力 |
| Structure | route_length         | 当前作业工序数   | int   | `/max_op`                     | 泛化不同工艺 |
| Structure | capacity_mismatch    | 前后段能力比     | float | `front_cap / rear_cap`        | 判断瓶颈     |
| Structure | downstream_pressure  | 下游负载压力     | float | `rear_wip / rear_parallelism` | 控制 release |

------

# 5 建议保留的晶圆级特征

如果你仍然保留 wafer-level 表示。

| 特征                    | 含义             | 归一化          |
| ----------------------- | ---------------- | --------------- |
| loc_onehot              | 当前所在设备     | one-hot         |
| remaining_process_ratio | 剩余加工比例     | `/proc_time`    |
| remaining_slack_ratio   | 剩余驻留时间比例 | `/hold_limit`   |
| stage_index_ratio       | 当前工序位置     | `/route_length` |

------

# 6 这些特征解决的核心策略

| 目标策略                  | 关键观测                                                     |
| ------------------------- | ------------------------------------------------------------ |
| 后段慢 → 前段主动延迟     | `rear_busy_ratio` `downstream_pressure` `rear_avg_remaining_time` |
| 前段机器多 → 控制 release | `capacity_mismatch` `buffer_occ`                             |
| 避免 buffer 堵塞          | `buffer_occ` `llc_congestion_ratio`                          |
| 避免驻留违规              | `remaining_slack_ratio` `urgent_wafers_ratio`                |
| 适应不同设备结构          | `front_parallelism` `rear_parallelism`                       |

------

# 7 推荐最终 obs 结构

建议按 **5块拼接**

```
[PM/TM/Buffer局部特征]
+
[Front stage summary]
+
[Rear stage summary]
+
[LLC/LLD interface特征]
+
[全局结构特征]
```

------

如果你愿意，我可以再帮你把这张表 **压缩成一份“最小可行 obs（20~30维）”设计**，这样既能泛化，又不会让状态维度爆炸。