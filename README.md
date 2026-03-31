# NDE_R_E

Developed with Unreal Engine 5

角色蓝图: /Game/FirstPerson/Blueprints/BP_FirstPersonCharacter_01//
所有可交互项目：/Game/LevelPrototyping/Interactable//
其中Walls文件夹里面的BP_Wall能够阻挡玩家和方块，而BP_InvisibleWall只能阻挡方块。两种墙都可以通过默认栏目下的设置来切换可见性//
InterFaces中的接口是玩家与物体交互时的内容//
Data中的GravityDir为一个数组，有7个值。0为向下，6为无重力。如果看见类似NowDir之类的整数变量，就是用来选择这个的。//
与关卡相关的内容放在FirstPerson中。关于可交互的物体，接口放在LevelPrototyping/Interactable/InterFaces下。//
对于多对多的交互设计，使用/Script/Engine.Blueprint'/Game/FirstPerson/MechanismTest/BP_GlobalEventDIspatcher.BP_GlobalEventDIspatcher'。请在其中声明事件分发器//
/Game/FirstPerson/Levels是存正式关卡的文件夹
/Game/FirstPerson/MechanismTest保存了测试机制用的关卡
