# NDE\_R\_E

Developed with Unreal Engine 5

角色蓝图: /Game/FirstPerson/Blueprints/BP\_FirstPersonCharacter\_01//
所有可交互项目：/Game/LevelPrototyping/Interactable//
其中Walls文件夹里面的BP\_Wall能够阻挡玩家和方块，而BP\_InvisibleWall只能阻挡方块。两种墙都可以通过默认栏目下的设置来切换可见性//
InterFaces中的接口是玩家与物体交互时的内容//
Data中的GravityDir为一个数组，有7个值。0为向下，6为无重力。如果看见类似NowDir之类的整数变量，就是用来选择这个的。//
与关卡相关的内容放在FirstPerson中。关于可交互的物体，接口放在LevelPrototyping/Interactable/InterFaces下。//
对于多对多的交互设计，使用/Script/Engine.Blueprint'/Game/FirstPerson/MechanismTest/BP\_GlobalEventDIspatcher.BP\_GlobalEventDIspatcher'。请在其中声明事件分发器//
/Game/FirstPerson/Levels是存正式关卡的文件夹
/Game/FirstPerson/MechanismTest保存了测试机制用的关卡



2026/04/20更新

如果需要制作“只有模型不一样”的蓝图类，请不要复制或者拉一个子类出来，你可以改实例使用的网格//

所有的门都已经移动到/Game/LevelPrototyping/Interactable/Doors，请尽量以StandardDoor文件夹中的那个门为基础去写其他的门//

不要在没有提交修改的情况下随意切换分支！大概率会丢失工作内容！如果要切，请确保自己知道自己的操作会导致什么后果！！！//

删除了大部分关于视角谜题的蓝图和资产，现在他们应该不能在游戏中正常运行



