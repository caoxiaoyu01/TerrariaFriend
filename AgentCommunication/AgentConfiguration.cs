using System;

namespace TerrariaFriend.AgentCommunication
{
	// Agent 地址与网络参数集中放置，避免散落在业务代码中。
	public static class AgentConfiguration
	{
		public static readonly Uri TriggerEndpoint = new Uri("http://127.0.0.1:8000/agent/trigger");
		public static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(10);
	}
}
