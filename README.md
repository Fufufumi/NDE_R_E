# NDE_R_E

Developed with Unreal Engine 5

角色蓝图: /Game/FirstPerson/Blueprints/BP_FirstPersonCharacter_01
所有可交互项目：/Game/LevelPrototyping/Interactable
其中Walls文件夹里面的BP_Wall能够阻挡玩家和，而BP_InvisibleWall只能阻挡方块。两种墙都可以通过默认栏目下的设置来切换可见性
InterFaces中的接口是玩家与物体交互时的内容
Data中的GravityDir为一个数组，有7个值。0为向下，6为无重力。如果看见类似NowDir之类的整数变量，就是用来选择这个的。
BP_GravityButton尚不完善，目前场景中最多只能有一个按钮
角色行走尚不完善。
