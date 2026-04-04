// Fill out your copyright notice in the Description page of Project Settings.


#include "MyChaosCachePlayer.h"

void AMyChaosCachePlayer::ForceRefreshPhysicsForObservedComponents()
{
	for (const FObservedComponent& ObservedComponent : ObservedComponents)
	{
		if (UGeometryCollectionComponent* GeomComp = Cast<UGeometryCollectionComponent>(ObservedComponent.Component.Get()))
		{
			// 销毁并重新创建物理状态
			GeomComp->RecreatePhysicsState();
			// 可选：强制更新碰撞过滤器
			GeomComp->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Block);
			GeomComp->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
			GeomComp->SetSimulatePhysics(true);
		}
	}
}