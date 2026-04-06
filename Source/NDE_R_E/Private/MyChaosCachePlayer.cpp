// Fill out your copyright notice in the Description page of Project Settings.


#include "MyChaosCachePlayer.h"
#include "GeometryCollection/GeometryCollectionComponent.h"  
#include "Chaos/CacheManagerActor.h"                         

void AMyChaosCachePlayer::ForceRefreshPhysicsForObservedComponents()
{
	const TArray<FObservedComponent> & ComponentArray=GetObservedComponents();
	for (const FObservedComponent& ObservedComponent : ComponentArray )
	{
		if (UGeometryCollectionComponent* GeomComp = Cast<UGeometryCollectionComponent>(ObservedComponent.GetComponent(this)))
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