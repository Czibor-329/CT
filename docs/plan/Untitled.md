先说结论：你现在这个“事后追责 + 最近 4 个 batch 平均间隔 + 强制最小间隔”的问题，不只是均值太粗，而是它把**配方本身的能力**和**当时系统状态造成的额外等待**混在一起了。你学到的不是 recipe 的真实节拍，而是

```
recipe + 下游拥堵 + 清洗相位 + Buffer 状态 + 机器人等待策略
```

的混合量，所以一旦某个 batch 因为清洗、Buffer 堵塞、TM 持片等待而出现极端大间隔，这个值就会被写进后续 batch，直接把 makespan 拉坏。

更关键的是，在多配方 cluster tool 里，性能会随着 **wafer release sequence** 和 **robot task sequence** 改变；带 buffer 的 multi-cluster tool 在 residency constraints 下更复杂；cleaning 和 processing-time variation 会改变平均 cycle time；此外 bottleneck 还会漂移。所以“每个 recipe 一个固定节拍常数”在你的场景里通常并不成立。([科学直通车](https://www.sciencedirect.com/science/article/pii/S0957417425018299))

另外，你优化的是 **finite batch 的 makespan**，而 cluster tool 天然有 **start-up、steady-state、close-down** 三段。头几片是填充期，末几片是排空期，中间才是稳态；把整批数据压成一个平均 interval，必然会把三段混偏。([科学直通车](https://www.sciencedirect.com/science/article/pii/S1383762122002739))

我会建议你不要再找“单一节拍值”，而是改成学一个三层结构：
$$
[
\tau(r,s,\phi)=\tau^{base}(r,\pi,\phi)+\Delta^{mode}(z)+w^*(s,r)
]
$$
这里：

- (r)：当前配方
- ($\pi$)：配方上下文，至少建议带上前一片/当前主配方类型
- ($\phi$)：批次阶段，start / mid / tail
- (z)：模式，normal / pre-clean / cleaning / buffer-congested / TM-hold
- ($w^*(s,r)$)：根据当前状态算出来的即时等待

也就是说，你真正该学的不是“recipe 的固定节拍”，而是**在当前状态下这片 wafer 最小应该晚多久放行**。

### 1. 先把“基础节拍”离线求出来

这个部分尽量不要从当前策略跑出来的实际间隔里学，因为那个间隔已经被你现在的 wait 动作污染了。

更靠谱的方法是对每个配方，或者更进一步对每个 **配方转移** (i \rightarrow j)，做一个**周期放行搜索**：

1. 固定 sequence，比如全是 recipe (r)，或者固定成 (i,j,i,j) / (i,i,j) 这类你实际会出现的模式。
2. 设一个周期放行间隔 (h)。
3. 在离散事件仿真器里跑足够长，至少覆盖完整清洗超周期。
4. 判定 (h) 是否可行：
   - 无驻留时间违约
   - LLC/LLD 不出现持续性失控堆积
   - 下游无长期 blockage 扩散
   - 单片平均完成时间进入稳定
5. 对 (h) 做二分搜索，找到最小可行 (h^*)。

这样得到的是：

[
\tau^{base}(r,\pi,\phi)
]

其中 (\pi) 至少建议先用“前一片 recipe”，因为多配方场景下 sequence 本身就影响性能。([科学直通车](https://www.sciencedirect.com/science/article/pii/S0957417425018299))

一个很实用的起步版本是：

- 单 recipe 表：(\tau^{base}(r))
- 二元转移表：(\tau^{base}(i \rightarrow j))
- 再乘上 phase：start / mid / tail

也就是变成：

[
\tau^{base}(i \rightarrow j,\phi)
]

这通常就已经比“每个 batch 一个平均间隔”稳很多了。

### 2. 在线不要用固定最小间隔，改成“预测下游最早可接收时刻”

你的核心问题其实是**前段放得太早，下游接不住**。
那最直接的办法不是记历史平均，而是每次都算：

- 如果现在放这片，它什么时候到 LLC / LLD / PM7–PM10？
- 下游什么时候真正能接它？

定义：
$$
[
\hat t^{arr}(s,r)=\text{现在放行后，这片到达下游交接点的预测时刻}
]
$$

$$
[
\hat t^{acc}(s,r)=\text{下游真正最早可接收这片的预测时刻}
]
$$

那么你应该加的等待不是“最近几批的均值”，而是
$$
[
w^*(s,r)=\max{0,\ \hat t^{acc}(s,r)-\hat t^{arr}(s,r)-\delta_r}
]
$$
这里 (\delta_r) 是安全裕量，防止过紧。

对你的级联设备，(\hat t^{acc}) 至少要看这几件事：

- PM7–PM10 的 next-free time
- TM2 的可服务时间
- LLC / LLD 的剩余容量和 next-free time
- 这片进去后是否会触发某个下游 PM 的 cleaning
- 当前 residence slack 是否允许它在 Buffer 或 TM 上等

于是最终放行条件变成：

[
\text{release only if } elapsed \ge \max{\tau^{base}(r,\pi,\phi),\ w^*(s,r)}
]

这就从“固定节拍控制”变成了**JIT 放行控制**。
它天然就带了你想要的“下游瓶颈感知”和“Buffer 合理利用”。

工厂控制里更稳的思路也确实是动态 release control / adaptive CONWIP：放行节奏跟着当前 WIP 或实时状态走，而不是固定间隔；也有工作直接把 release control 和 scheduling 合在一起做动态决策。([Springer](https://link.springer.com/article/10.1007/s00170-013-4762-y))

### 3. 清洗 every 3 wafers 这种情况，不要再逼自己找单一常数节拍

你这个担忧是对的。
只要存在“每处理 3 片就要清洗一次”的机制，节拍就不是常数，而是**模式切换值**。

最简单的做法是把每个 PM 的“清洗年龄”显式入状态：

- `remain_to_clean[k]`：PM k 距离下次 clean 还差几片
- `clean_busy_until[k]`
- `effective_free_time[k]`

然后把模式至少分成两类：

- `normal`
- `pre-clean`（再来一片就会触发 clean）

于是你不是学 ($\tau_r$)，而是学
$$
[
\tau_{r,z}, \quad z \in {\text{normal},\text{pre-clean},\text{cleaning},\text{buffer-congested}}
]
$$
如果想再简化一点，先做这两个值就够了：
$$
[
\tau^{normal}_r,\quad \tau^{preclean}_r
]
$$
并且可以用一个平均下界初始化：
$$
[
p^{eff}*{k,r}=p*{k,r}+\frac{c_k}{N_k}
]
$$
其中 (p_{k,r}) 是 recipe 在 PM k 的加工时间，(c_k) 是 cleaning 时间，(N_k) 是每多少片清一次。这个值适合做**初始下界**，但真正放行仍应由上面的 ($\hat t^{acc}$) 决定，因为 pre-clean 那一拍会突然跳大。

这也是为什么实践里会讨论 **condition-based cleaning**：清洗本来就是一个显式影响产能与质量折中的模式变量，不该被揉进一个全局平均节拍里。([IDEAS/RePEc](https://ideas.repec.org/a/taf/tprsxx/v60y2022i11p3555-3568.html))

### 4. 你的“追责”思路可以保留，但要改成反事实标签，不要用 batch 均值

你现在的追责，本质是在做 credit assignment，这个方向没错。
错在标签太粗。

比“记录这批 u_LP 的平均间隔”更好的标签是：

[
d_t^*=\min{d\ge 0:\ \text{把第 }t\text{ 次 }u_{LP}\text{ 延后 }d\text{ 后，不再造成额外下游堵塞}}
]

也就是说，对每个可疑早放行动作，找出**最小必要延迟**，而不是记录“这批最后实际隔了多久”。

如果你的仿真器能 clone state，最好的做法是：

1. 动作发生时存快照
2. 事后从快照做几个局部回放：delay = 0, 1, 2, …
3. 找到最小能消除额外 blockage 的 delay
4. 把这个 (d_t^*) 记到 `(recipe, prev_recipe, phase, clean_mode, downstream_state_bucket)` 上

然后更新不要再用均值，改成：

- **中位数 / 分位数**
- 或者 **clipped EWMA**

例如：

[
\tau \leftarrow \tau + \alpha \cdot \mathrm{clip}(d_t^*-\tau,\ -\Delta_-,\ \Delta_+)
]

并且让 (\Delta_+) 小一点，防止偶发极端大等待把节拍顶飞。

更进一步，你可以把“基础节拍”和“异常裕量”分开存：

[
\tau^{base} = Q_{0.5}(d_t^*)
]

[
margin = Q_{0.9}(d_t^*) - Q_{0.5}(d_t^*)
]

这样 rare event 只会增加安全裕量，不会永久抬高 base pace。

### 5. 你现在的动作空间也在“污染节拍”

你自己已经点到了：有时候 wafer 在 TM 上停太久，学出来的节拍就会很大。

这说明当前观测到的间隔里，混了很多**策略自造的 idling**。
所以有两个改法非常重要：

第一，**把 wait 分位置**，不要只分时长：

- `wait-before-pick`
- `wait-in-buffer`
- `wait-on-TM`

这三种等待对系统的伤害完全不同。
`wait-on-TM` 会占住机器人，是最不应该被当成 recipe 节拍的一种等待。

第二，给 `wait-on-TM` 加单独约束：

- 要么硬上限，比如不能超过很小阈值
- 要么单独重罚：

$$
[
r_t \leftarrow r_t - \lambda_{tm}\cdot t^{hold}_{TM}
]
$$

这样 agent 会更愿意在 LLC / LLD 等，或者在 release 之前等，而不是把 wafer 挂在 TM 上。

如果继续走 RL，这一块其实更适合用“目标对齐时刻”而不是“离散 wait 档位”做动作。也就是动作不再是“等 0/1/2/3 档”，而是“把到达 LLC/LLD 的时间对齐到下游 next accept slot”。近期也确实有把 release control 设计成更连续、更状态相关动作的做法。([Springer](https://link.springer.com/article/10.1007/s40747-022-00844-0))

### 6. 一个最小改动版本

如果你暂时不想大改框架，我建议先只做这 4 个改动：

1. **按 recipe 分桶**，至少做到 `recipe × phase(start/mid/tail) × clean_mode(normal/pre-clean)`。
2. **把 batch 平均间隔改成 counterfactual minimal delay 的中位数**，别再用均值。
3. **在 u_LP 前加一个 downstream earliest-accept gate**：
   只有当预测到达时刻不早于下游可接收时刻太多，才允许开工。
4. **限制 wait-on-TM**，超长等待只能发生在 release 前或 Buffer 中，不能发生在 TM 持片中。

这样改完以后，你会发现两件事：

- rare clean / 极端拥堵不会再永久把 recipe 节拍抬高
- 策略学到的会更像“何时放行”，而不是“盲目把所有前段都放慢”

一句话总结：
你现在要学的不是“每个配方一个固定节拍值”，而是**每个配方在不同 phase / clean mode / downstream 状态下的最小安全放行延迟**。这比 batch 均值强很多，也更接近你真正想要的下游瓶颈感知。

下一步最值得做的，是把 `u_LP` 从“固定最小间隔”改成“预测下游可接收时刻的 JIT 放行”。