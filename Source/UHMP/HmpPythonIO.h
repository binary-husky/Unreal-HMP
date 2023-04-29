// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Jsonx.h"
#include "Networking.h"
#include "JsonxObjectConverter.h"
#include "Containers/UnrealString.h"
#include "GenericPlatform/GenericPlatformMisc.h"
#include "GameFramework/Actor.h"
#include "Misc/UObjectToken.h"
#include "IOCompress/lz4.h"
#include "DataStruct.h"
#include "libipc/ipc.h"
#include "HmpPythonIO.generated.h"


class ShareMemServer
{
public:
	std::string server_listen_channel;
	std::string client_listen_channel;
	std::atomic<bool> is_quit__{ false };

	ipc::channel* server_listen_ipc = nullptr;
	ipc::channel* client_listen_ipc = nullptr;
	bool debug = true;


	ShareMemServer(std::string channel, bool debug_network) { // Constructor with parameters
		debug = debug_network;
		server_listen_channel = channel + "-server";
		client_listen_channel = channel + "-client";
		if (debug)
		{
			std::cout << "server_listen_channel: " << server_listen_channel << std::endl;
			std::cout << "client_listen_channel: " << client_listen_channel << std::endl;
		}
		server_listen_ipc = new ipc::channel{ server_listen_channel.c_str(), ipc::receiver };
		client_listen_ipc = new ipc::channel{ client_listen_channel.c_str(), ipc::sender };
	}
	~ShareMemServer() {
		server_listen_ipc->disconnect();
		client_listen_ipc->disconnect();
		if (debug)
		{
			std::cout << "server_listen_ipc->disconnect(); " << std::endl;
			std::cout << "client_listen_ipc->disconnect(); " << std::endl;
		}
	}
public:
	std::string wait_next_dgram()
	{
		if (debug)
		{
			std::cout << "wait_next_dgram" << std::endl;
		}
		ipc::buff_t recv = server_listen_ipc->recv();
		std::string dat{ recv.get<char const*>(), recv.size() - 1 };
		if (debug)
		{
			std::cout << "[wait_next_dgram] get data" << dat << std::endl;
		}
		return dat;
	}

	void reply(std::string reply_buffer) {
		if (debug)
		{
			std::cout << "reply sending: " << reply_buffer << std::endl;
		}
		bool success = client_listen_ipc->try_send(reply_buffer, 0/*tm*/);
		if (debug)
		{
			std::cout << "reply success?" << success << std::endl;
		}

	}

};



UCLASS()
class UHMP_API AHmpPythonIO : public AActor
{
	GENERATED_BODY()

public:
	// Sets default values for this actor's properties
	AHmpPythonIO();

protected:
	void BeginDestroy() override;

	// Tcp server start
	FSocket* ListenSocket = NULL;
	FSocket* TcpAccpetedSocket = NULL;

	UPROPERTY(BlueprintReadWrite)
		float SendBufferUsage = 0.0f;
	UPROPERTY(BlueprintReadWrite)
		float RecvBufferUsage = 0.0f;


	std::string channelx = "debug2";
	ShareMemServer *server = new ShareMemServer("debug2", false);

	double tic_second = 0.0f;
	double toc_second = 0.0f;

	double dur_tic_second = 0.0f;
	double dur_toc_second = 0.0f;
	double dur_sum_second = 0.0f;

	int32 SendBufferSize = 1024 * 1024 * 16;
	int32 ReceiveBufferSize = 1024 * 1024 * 16;
	uint8* SendBuffer = new uint8[SendBufferSize];
	uint8* RecvBuffer = new uint8[ReceiveBufferSize];
	uint8* RecvDecompressBuffer = new uint8[ReceiveBufferSize];

	// Tcp server send out json (Blocked)
	void TcpServerSendJson(TSharedPtr<FJsonxObject> ReplyJson, float& encTime, float& sendTime);
	// Warning, do not use this func!
	UFUNCTION(BlueprintCallable)
		void DisableRendering();
	// Warning, do not use this func!
	UFUNCTION(BlueprintCallable)
		void EnableRendering();
	
	// In order to make sure that game is invariant to machine performance
	// there are several thing need to do
	// <1> Fixed the frame rate in project setting -> engine -> general
	// <2> Set frame rate by writing GEngine->FixedFrameRate
	// <3> Set Global Time Dilation by UGameplayStatics::SetGlobalTimeDilation(WorldContext)
	// Delta tick time is precisely ```dT = TimeDilation / FixedFrameRate```
	// Therefore, we must keep ```TimeDilation / FixedFrameRate``` constant
	// <void ChangeEngineFixedFrameRate(float fps)>: Change the fixed frame rate of Unreal Engine, 
	// Warning, please change it together with Time Dilation, or everything will fuck up, 2 <= fps <= 5000
	UFUNCTION(BlueprintCallable)
		void ChangeEngineFixedFrameRate(float fps);
	// Initialize Tcp Server at specific port
	UFUNCTION(BlueprintCallable)
		void StartTcpServer(int32 InListenPort);
	// Tcp server wait client (blocking)
	UFUNCTION(BlueprintCallable)
		void TcpServerWaitClient();
	// is any client waiting to connect
	UFUNCTION(BlueprintCallable)
		bool TcpServerHasWaitingClient();
	// convert Json, then it will call "TcpServerSendJson"
	UFUNCTION(BlueprintCallable)
		void ConvertOutDataToJsonAndSendTcp(TArray<FAgentDataOutput> TcpOutDataArr, FGlobalDataOutput GlobalData, 
			float& toJsonTime, float& encTime, float& sendTime);
	// Any Data to read
	UFUNCTION(BlueprintCallable)
		bool TcpServerHasRecvData();
	// sleep for wall-clock time, use with caution
	UFUNCTION(BlueprintCallable)
		void sleep_thread(float second);
	// receive tcp data (blocked)
	UFUNCTION(BlueprintCallable)
		FString TcpServerRecvBlocked(bool checkEOF, float& tcpWaitTime, float& decodeTime);
	// parse string read from tcp
	UFUNCTION(BlueprintCallable)
		FParsedDataInput ParsedTcpInData(FString TcpLatestRecvString);

	// exit game
	UFUNCTION(BlueprintCallable)
		void exit_hmp(bool force);

	UFUNCTION(BlueprintCallable)
		void tic();

	UFUNCTION(BlueprintCallable)
		float toc();


	UFUNCTION(BlueprintCallable)
		void dur_tic();

	UFUNCTION(BlueprintCallable)
		void dur_toc();

	UFUNCTION(BlueprintCallable)
		float dur_reset();


	UFUNCTION(BlueprintCallable, meta = (WorldContext = "WorldContextObject", CallableWithoutWorldContext, Keywords = "raise error", DevelopmentOnly), Category = "Utilities|Debugging")
		static void RaiseErrorNative(UObject* WorldContextObject, const FString& ErrorMessage = FString(TEXT("An error occurred")), bool bPrintToOutputLog = true);

};
