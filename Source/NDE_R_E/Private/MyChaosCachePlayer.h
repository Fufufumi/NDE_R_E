// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Chaos/CacheManagerActor.h"
#include "MyChaosCachePlayer.generated.h"

/**
 * 
 */
UCLASS()
class AMyChaosCachePlayer : public AChaosCachePlayer
{
	GENERATED_BODY()
public:
	UFUNCTION(BlueprintCallable, Category = "ChaosCache")
	void ForceRefreshPhysicsForObservedComponents();
};
