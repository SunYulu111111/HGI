# HGI 项目约定

## 按 model 生成主题

- 按 model 生成或调整主题前，先阅读 [README.md 的 model 生成与配置字段归属](README.md#model-生成与配置字段归属)，遵守其中的目录、配置协议、字段归属和数值填写规范。
- 主题特殊玩法新增字段只放在 `{name}_game_server.conf`；有独立 Bonus 玩法时生成 `{name}_bonus.conf` 存放 Bonus 专用配置；其他配置文件不加入对应 model 之外的字段。

## 新增字段命名

- 本规则适用于 HGI 文件夹及其所有子目录中的新增内容。
- 所有新增字段统一使用大驼峰命名法（PascalCase）：每个单词的首字母大写，单词之间不使用下划线或连字符。
- 示例：`BaseBet`、`FreeSpinCount`、`TotalWin`、`BonusJpMultiple`。
- 适用范围包括配置字段、JSON / 字典键、数据结构属性、接口输入输出字段，以及文档、示例和生成脚本中的对应字段。
- 新增字段的定义、读写引用、测试及文档必须使用一致的 PascalCase 名称。
- 现有字段不因本规则自动批量改名；用户要求迁移时，再同步更新相关引用和兼容逻辑。
